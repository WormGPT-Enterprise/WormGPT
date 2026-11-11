"""Clean WORMGPT-compatible backend.

Implements the exact API contract the cloned frontend expects, backed by
NVIDIA NIM (OpenAI-compatible). No offensive-security endpoints, no
code-kit generators.
"""
import json, logging, os, time, hashlib
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import nvidia_client as nv
import platform_api
import completions
import community_api
import integrations
import runner
from chat_stream import stream_chat
from store import (SESSIONS, prune_sessions, session_create, set_password,
                   user_for as _user_for, verify_password)

load_dotenv()
BASE = Path(__file__).resolve().parent
SITE = BASE.parent / "site"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    prune_sessions()
    yield


app = FastAPI(title="WormGPT (clean rebuild)", lifespan=lifespan)
app.include_router(platform_api.router)
app.include_router(community_api.router)
app.include_router(integrations.router)
# OpenAI-compatible endpoint used by the Models playground; the UI tries
# /api/v1/... first and falls back to /v1/...
app.include_router(completions.router)
app.include_router(completions.router, prefix="/api")


def _json_error(message: str, status: int = 400):
    return JSONResponse({"error": message}, status)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """Return JSON for unhandled errors.

    Without this, a malformed body or a bad upstream raised out of the route and
    the client received an HTML ``text/plain`` 500. The frontend parses JSON, so
    it reported a misleading "invalid response" instead of the real cause.
    """
    logging.exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"error": "Internal server error."}, 500)


@app.middleware("http")
async def api_json_404(request: Request, call_next):
    """Kept for /v1 paths, which have no catch-all route of their own."""
    path = request.url.path
    if path.startswith("/v1/"):
        response = await call_next(request)
        if response.status_code == 404:
            return JSONResponse({"error": f"No such endpoint: {path}"}, 404)
        return response
    return await call_next(request)


@app.get("/api/public-config")
async def public_config():
    # Test site key: frontend skips Turnstile when it matches /^[123]x0{10,}/
    return {"turnstileSiteKey": "1x00000000000000000000AA"}


@app.post("/api/login")
async def login(req: Request):
    try:
        body = await req.json()
    except Exception:
        return _json_error("Request body must be valid JSON.")
    if not isinstance(body, dict):
        return _json_error("Request body must be a JSON object.")
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return JSONResponse({"error": "Username and password are required."}, 400)
    prune_sessions()
    known = verify_password(username, password)
    if known is False:
        return JSONResponse({"error": "Invalid username or password."}, 401)
    if known is None:
        # First login for this name registers the credential. A later login
        # with a different password is rejected.
        set_password(username, password)
    user = {"id": hashlib.sha1(username.encode()).hexdigest()[:12],
            "username": username, "email": username if "@" in username else ""}
    license_ = {"key": "CLEAN-REBUILD", "type": "lifetime", "credits": -1,
                "expires": None}
    token = session_create(user, license_)
    return {"success": True, "user": user, "license": license_, "token": token}


@app.post("/api/signup")
async def signup(req: Request):
    return await login(req)


@app.get("/api/session")
async def session(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "").strip()
    s = _user_for(token)
    if not s:
        return JSONResponse({"error": "Authentication token is required."}, 401)
    return {"success": True, "user": s["user"], "license": s["license"]}


@app.post("/api/logout")
async def logout(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "").strip()
    SESSIONS.pop(token, None)
    return {"success": True}


@app.get("/api/license")
async def license_(authorization: str = Header(default="")):
    s = _user_for(authorization.replace("Bearer ", "").strip())
    if not s:
        return JSONResponse({"error": "Authentication token is required."}, 401)
    return {"success": True, "license": s["license"]}


@app.get("/api/health")
async def health(authorization: str = Header(default="")):
    return {"success": True, "status": "ok", "provider": "WormGPT",
            "hasKey": nv.has_key()}


@app.get("/api/provider-status")
async def provider_status():
    return {"provider": "WormGPT", "model": "wormgpt-v6",
            **(await nv.check_access())}


@app.get("/api/models")
async def models():
    # White-label: never expose the real upstream model id or vendor to clients.
    out = []
    for alias in nv.MODEL_ALIASES:
        out.append({"id": alias, "name": alias, "provider": "WormGPT",
                    "status": "operational"})
    return {"object": "list", "data": out}


@app.post("/api/chat-proxy")
async def chat_proxy(req: Request, authorization: str = Header(default="")):
    s = _user_for(authorization.replace("Bearer ", "").strip())
    if not s:
        return JSONResponse({"error": "Authentication token is required."}, 401)
    try:
        body = await req.json()
    except Exception:
        return _json_error("Request body must be valid JSON.")
    if not isinstance(body, dict):
        return _json_error("Request body must be a JSON object.")
    messages = body.get("messages")
    if messages is not None and not isinstance(messages, list):
        return _json_error("`messages` must be a list.")
    return StreamingResponse(stream_chat(body), media_type="text/event-stream")


@app.get("/api/run/capabilities")
async def run_capabilities():
    return {"success": True, "runtimes": runner.supported()}


@app.post("/api/run")
async def run_code(req: Request, authorization: str = Header(default="")):
    """Run a workspace file server-side (the IDE Run button calls this)."""
    s = _user_for(authorization.replace("Bearer ", "").strip())
    if not s:
        return JSONResponse({"error": "Authentication token is required."}, 401)
    body = await req.json()
    files = body.get("files")
    if not isinstance(files, list) or not files:
        return JSONResponse({"error": "No files to run."}, 400)
    result = runner.run_files(files, body.get("entry"))
    return JSONResponse(result, 200)



@app.get("/api/chats")
async def chats_get(authorization: str = Header(default="")):
    s = _user_for(authorization.replace("Bearer ", "").strip())
    if not s:
        return JSONResponse({"error": "Authentication token is required."}, 401)
    return {"success": True, "chats": []}


@app.post("/api/chats")
async def chats_post(req: Request, authorization: str = Header(default="")):
    s = _user_for(authorization.replace("Bearer ", "").strip())
    if not s:
        return JSONResponse({"error": "Authentication token is required."}, 401)
    body = await req.json()
    return {"success": True, "chat": {"id": "local", **body}}


@app.post("/api/chats-wipe")
async def chats_wipe(authorization: str = Header(default="")):
    s = _user_for(authorization.replace("Bearer ", "").strip())
    if not s:
        return JSONResponse({"error": "Authentication token is required."}, 401)
    return {"success": True}


from fastapi.responses import FileResponse


@app.get("/integrations")
async def integrations_page():
    return FileResponse(str(SITE / "integrations.html"))


@app.get("/{path:path}")
async def spa(path: str):
    # An unimplemented /api/* endpoint must not fall through to the SPA shell:
    # it answered 200 text/html, so JSON clients reported a bogus parse error.
    if path.startswith("api/") or path.startswith("v1/"):
        return JSONResponse({"error": f"No such endpoint: /{path}"}, 404)
    target = (SITE / path).resolve()
    try:
        inside = target.is_relative_to(SITE.resolve())
    except AttributeError:  # pragma: no cover - Python < 3.9
        inside = str(target).startswith(str(SITE.resolve()))
    if path and inside and target.is_file():
        return FileResponse(str(target))
    return FileResponse(str(SITE / "index.html"))
