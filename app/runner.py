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
import shutil
import subprocess
import tempfile
from pathlib import Path

TIMEOUT_SECONDS = 20
MAX_OUTPUT_CHARS = 60_000

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
}

# language -> compiler argv; the binary is run afterwards.
COMPILERS = {
    "c": (["gcc", "{f}", "-O0", "-o", "main.bin"], "main.c"),
    "cpp": (["g++", "-std=c++17", "{f}", "-O0", "-o", "main.bin"], "main.cpp"),
    "rust": (["rustc", "--edition", "2021", "{f}", "-o", "main.bin"], "main.rs"),
}

LANGUAGE_BY_EXT = {
    "py": "python", "js": "javascript", "mjs": "javascript", "cjs": "javascript",
    "jsx": "jsx", "ts": "typescript", "tsx": "tsx", "php": "php",
    "sh": "bash", "bash": "bash", "rb": "ruby", "go": "go", "rs": "rust",
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
    }


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
                "error": f"Don't know how to run '{chosen}'. "
                         "Supported: Python, JavaScript, TypeScript, PHP, Bash, C, C++."}

    workdir = tempfile.mkdtemp(prefix="wormrun-")
    try:
        for name, content in staged:
            target = Path(workdir) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        if language in COMPILERS:
            argv, _ = COMPILERS[language]
            if not shutil.which(argv[0]):
                return {"ok": False, "language": language, "entry": chosen,
                        "error": f"'{argv[0]}' is not installed on this server."}
            compile_argv = [a.replace("{f}", chosen) for a in argv]
            comp = subprocess.run(compile_argv, cwd=workdir, capture_output=True,
                                  text=True, timeout=TIMEOUT_SECONDS)
            if comp.returncode != 0:
                out, cut = _truncate(comp.stdout + comp.stderr)
                return {"ok": False, "language": language, "entry": chosen,
                        "stdout": "", "stderr": out, "exitCode": comp.returncode,
                        "truncated": cut, "phase": "compile"}
            cmd = [os.path.join(workdir, "main.bin")]
        else:
            argv, _ = INTERPRETERS[language]
            if not shutil.which(argv[0]):
                return {"ok": False, "language": language, "entry": chosen,
                        "error": f"'{argv[0]}' is not installed on this server."}
            cmd = [a.replace("{f}", chosen) for a in argv]

        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS)
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
