"""Real VS Code integration and source-code access for the Lifetime plan.

These implement, for real, the two features the marketing pages advertise:

* ``GET  /api/integrations/vscode/config``    - connection details (base URL,
  model aliases) so any OpenAI-compatible client can be pointed at us.
* ``GET  /api/integrations/vscode/extension`` - the packaged ``.vsix``.
* ``GET  /api/integrations/source/manifest``  - what the source bundle holds.
* ``GET  /api/integrations/source/download``  - a ZIP of this repository's
  source, gated to Lifetime licenses.

The API key is never returned here: the caller creates one in the API
Platform, exactly like every other endpoint expects.
"""
import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response

from store import token_from_header, user_for

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
VSIX = ROOT / "vscode-extension" / "dist" / "wormgpt-vscode.vsix"

VSCODE_MODELS = ["wormv6.2", "wormv6.1", "wormv6", "wormv5.2", "wormv5.1",
                 "wormv5.0", "wormv4.1", "wormv4.0"]

# Never ship secrets, caches, local toolchains, build output or backups.
EXCLUDE_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache",
                ".mypy_cache", ".ruff_cache", "dist", ".openhands",
                ".agents_tmp", "reference"}
EXCLUDE_SUFFIXES = {".orig", ".pyc", ".pyo", ".log", ".vsix", ".map"}
EXCLUDE_FILES = {".env", "WormGPT"}


def _session(authorization: str):
    return user_for(token_from_header(authorization))


def _has_source_access(session) -> bool:
    lic = (session or {}).get("license") or {}
    return lic.get("type") in ("lifetime",) or bool(lic.get("sourceIncluded"))


def _request_base(req) -> str:
    proto = req.headers.get("x-forwarded-proto", req.url.scheme)
    host = req.headers.get("host", req.url.netloc)
    return f"{proto}://{host}"


@router.get("/vscode/config")
async def vscode_config(req: Request):
    base = _request_base(req)
    return {
        "success": True,
        "vendor": "wormgpt",
        "displayName": "WormGPT",
        "baseUrl": f"{base}/v1",
        "chatCompletionsUrl": f"{base}/v1/chat/completions",
        "modelsUrl": f"{base}/api/models",
        "apiKeyHeader": "Authorization: Bearer <wrm_live_...>",
        "models": VSCODE_MODELS,
        "vsixUrl": f"{base}/api/integrations/vscode/extension",
        "install": [
            "Download wormgpt-vscode.vsix",
            "VS Code -> Extensions -> ... -> Install from VSIX",
            "Run command 'WormGPT: Set API Key' and paste your wrm_ key",
            "Open the Chat view and pick the WormGPT provider",
        ],
    }


@router.get("/vscode/extension")
async def vscode_extension():
    if not VSIX.exists():
        return JSONResponse(
            {"error": "Extension bundle is not built. Run .tools/build_vsix.py."},
            503)
    return Response(
        VSIX.read_bytes(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="wormgpt-vscode.vsix"'},
    )


def _iter_source():
    """Yield (absolute path, archive name) for every file we may ship."""
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        parts = rel.parts
        if any(p in EXCLUDE_DIRS for p in parts[:-1]) or rel.name in EXCLUDE_FILES:
            continue
        if rel.suffix in EXCLUDE_SUFFIXES:
            continue
        if rel.name.startswith(".") and rel.name != ".env.example":
            continue
        yield path, rel.as_posix()


def _build_source_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, arc in _iter_source():
            z.write(path, f"wormgpt/{arc}")
    return buf.getvalue()


@router.get("/source/manifest")
async def source_manifest(authorization: str = Header(default="")):
    session = _session(authorization)
    files = [{"path": arc, "bytes": p.stat().st_size} for p, arc in _iter_source()]
    return {
        "success": True,
        "requiresLifetime": True,
        "authorized": _has_source_access(session),
        "fileCount": len(files),
        "totalBytes": sum(f["bytes"] for f in files),
        "files": files,
    }


@router.get("/source/download")
async def source_download(authorization: str = Header(default="")):
    session = _session(authorization)
    if not session:
        return JSONResponse({"error": "Authentication token is required."}, 401)
    if not _has_source_access(session):
        return JSONResponse(
            {"error": "Full Source Code Access requires the Lifetime plan."}, 403)
    return Response(
        _build_source_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="wormgpt-source.zip"'},
    )
