"""Execute workspace files server-side so the IDE Run button works.

The upstream IDE only previews HTML in the browser and answers every other
language with "other runtimes require a sandbox service". This module is that
service: it takes a small set of files, writes them to a throwaway directory
and runs the entry point with the interpreter/compiler actually installed on
the host (python3, node, gcc, g++, php, bash).

Only the languages below are ever invoked, always via an argument vector (no
shell), inside a temporary directory that is removed afterwards.
"""
import os
import resource
import shutil
import subprocess
import tempfile
from pathlib import Path

TIMEOUT_SECONDS = 20
MAX_OUTPUT_CHARS = 60_000

# The runner executes user-supplied code on the host, so it is not a real
# sandbox. These limits at least stop the obvious abuses: the child inherits
# the server's environment (which holds NVIDIA_API_KEY after load_dotenv), and
# an unbounded child can take the worker down.
SECRET_HINTS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASSWD", "CREDENTIAL")
# Memory and CPU caps for the child process.
CHILD_ADDRESS_SPACE = 1_500_000_000   # ~1.5 GB
CHILD_CPU_SECONDS = TIMEOUT_SECONDS * 2


def _child_env() -> dict:
    """Environment for the child: drop anything that looks like a credential."""
    env = {}
    for name, value in os.environ.items():
        upper = name.upper()
        if any(hint in upper for hint in SECRET_HINTS):
            continue
        env[name] = value
    # Keep the interpreters usable without leaking the parent's secrets.
    env.setdefault("HOME", "/tmp")
    env.setdefault("PATH", os.environ.get("PATH", "/usr/bin:/bin"))
    return env


def _apply_limits():  # pragma: no cover - runs in the forked child
    try:
        resource.setrlimit(resource.RLIMIT_AS,
                           (CHILD_ADDRESS_SPACE, CHILD_ADDRESS_SPACE))
        resource.setrlimit(resource.RLIMIT_CPU,
                           (CHILD_CPU_SECONDS, CHILD_CPU_SECONDS))
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16_000_000, 16_000_000))
    except (ValueError, OSError):
        pass


# language -> (argv, filename) for a single-file run. `{f}` is the file path.
INTERPRETERS = {
    "python": (["python3", "{f}"], "main.py"),
    "javascript": (["node", "{f}"], "main.js"),
    "jsx": (["node", "{f}"], "main.jsx"),
    "typescript": (["node", "{f}"], "main.ts"),
    "tsx": (["node", "{f}"], "main.tsx"),
    "php": (["php", "{f}"], "main.php"),
    "bash": (["bash", "{f}"], "main.sh"),
    "ruby": (["ruby", "{f}"], "main.rb"),
    "go": (["go", "run", "{f}"], "main.go"),
    "lua": (["lua5.4", "{f}"], "main.lua"),
}

# language -> (compile argv, run argv); `{f}` is the entry file path.
COMPILERS = {
    "c": (["gcc", "{f}", "-O0", "-o", "main.bin"], ["./main.bin"]),
    "cpp": (["g++", "-std=c++17", "{f}", "-O0", "-o", "main.bin"], ["./main.bin"]),
    "rust": (["rustc", "--edition", "2021", "{f}", "-o", "main.bin"], ["./main.bin"]),
    # javac names the output after the public class, so the run command is fixed
    # to the conventional `Main` class the starter template defines.
    "java": (["javac", "{f}"], ["java", "-cp", ".", "Main"]),
    "csharp": (["mcs", "{f}", "-out:main.exe"], ["mono", "main.exe"]),
}

LANGUAGE_BY_EXT = {
    "py": "python", "js": "javascript", "mjs": "javascript", "cjs": "javascript",
    "jsx": "jsx", "ts": "typescript", "tsx": "tsx", "php": "php",
    "sh": "bash", "bash": "bash", "rb": "ruby", "go": "go", "rs": "rust",
    "lua": "lua", "java": "java", "cs": "csharp",
    "c": "c", "cpp": "cpp", "cc": "cpp", "cxx": "cpp", "h": "cpp", "hpp": "cpp",
}


def language_for(name: str) -> str:
    return LANGUAGE_BY_EXT.get(Path(name).suffix.lstrip(".").lower(), "")


def supported() -> dict:
    """Which runtimes this host can actually execute right now."""
    return {
        "python": bool(shutil.which("python3")),
        "javascript": bool(shutil.which("node")),
        "typescript": bool(shutil.which("node")),
        "php": bool(shutil.which("php")),
        "bash": bool(shutil.which("bash")),
        "c": bool(shutil.which("gcc")),
        "cpp": bool(shutil.which("g++")),
        "ruby": bool(shutil.which("ruby")),
        "go": bool(shutil.which("go")),
        "rust": bool(shutil.which("rustc")),
        "lua": bool(shutil.which("lua5.4")),
        "java": bool(shutil.which("javac") and shutil.which("java")),
        "csharp": bool(shutil.which("mcs") and shutil.which("mono")),
    }


def _have_command(token: str, workdir: str) -> bool:
    """True when `token` resolves — either a system binary or a just-built file."""
    if token.startswith("./"):
        return (Path(workdir) / token[2:]).exists()
    return bool(shutil.which(token))


def _safe_relpath(name: str) -> str | None:
    """Reject absolute paths and traversal so nothing escapes the temp dir."""
    clean = name.replace("\\", "/").lstrip("/")
    parts = [p for p in clean.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    return "/".join(parts) or None


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text, False
    return text[:MAX_OUTPUT_CHARS] + "\n… output truncated …", True


def run_files(files: list[dict], entry: str | None = None) -> dict:
    """Run `entry` (or the first runnable file) with the other files beside it.

    `files` is the frontend shape: [{"name": ..., "content": ...}, ...].
    Returns {ok, language, entry, stdout, stderr, exitCode, truncated, error}.
    """
    staged: list[tuple[str, str]] = []
    for f in files or []:
        name = _safe_relpath(str(f.get("name", "")))
        if name is None:
            continue
        staged.append((name, str(f.get("content", ""))))

    if entry:
        entry = _safe_relpath(entry)
    chosen = entry
    if not chosen or not any(n == chosen for n, _ in staged):
        chosen = next((n for n, _ in staged if language_for(n)), None)
    if not chosen:
        return {"ok": False, "error": "No runnable file in the workspace."}

    language = language_for(chosen)
    if not language:
        return {"ok": False, "entry": chosen,
                "error": f"Don't know how to run '{chosen}'. Supported: Python, "
                         "JavaScript, TypeScript, PHP, Bash, Ruby, Go, Rust, Lua, "
                         "Java, C#, C, C++."}

    workdir = tempfile.mkdtemp(prefix="wormrun-")
    try:
        for name, content in staged:
            target = Path(workdir) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        if language in COMPILERS:
            compile_argv, run_argv = COMPILERS[language]
            if not shutil.which(compile_argv[0]):
                return {"ok": False, "language": language, "entry": chosen,
                        "error": f"'{compile_argv[0]}' is not installed on this server."}
            compile_argv = [a.replace("{f}", chosen) for a in compile_argv]
            comp = subprocess.run(compile_argv, cwd=workdir, capture_output=True,
                                  text=True, timeout=TIMEOUT_SECONDS,
                                  env=_child_env(), preexec_fn=_apply_limits)
            if comp.returncode != 0:
                out, cut = _truncate(comp.stdout + comp.stderr)
                return {"ok": False, "language": language, "entry": chosen,
                        "stdout": "", "stderr": out, "exitCode": comp.returncode,
                        "truncated": cut, "phase": "compile"}
            if not _have_command(run_argv[0], workdir):
                return {"ok": False, "language": language, "entry": chosen,
                        "error": f"'{run_argv[0]}' is not installed on this server."}
            cmd = [a.replace("{f}", chosen) for a in run_argv]
        else:
            argv, _ = INTERPRETERS[language]
            if not shutil.which(argv[0]):
                return {"ok": False, "language": language, "entry": chosen,
                        "error": f"'{argv[0]}' is not installed on this server."}
            cmd = [a.replace("{f}", chosen) for a in argv]

        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS,
                              env=_child_env(), preexec_fn=_apply_limits)
        stdout, cut1 = _truncate(proc.stdout)
        stderr, cut2 = _truncate(proc.stderr)
        return {"ok": proc.returncode == 0, "language": language, "entry": chosen,
                "stdout": stdout, "stderr": stderr, "exitCode": proc.returncode,
                "truncated": cut1 or cut2, "phase": "run"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "language": language, "entry": chosen,
                "error": f"Execution timed out after {TIMEOUT_SECONDS}s."}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "language": language, "entry": chosen,
                "error": f"Runner error: {exc}"}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
