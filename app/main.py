"""Clean WORMGPT-compatible backend.

Implements the exact API contract the cloned frontend expects, backed by
NVIDIA NIM (OpenAI-compatible). No offensive-security endpoints, no
code-kit generators.
"""
import json, os, secrets, time, hashlib
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import nvidia_client as nv
import platform_api
import completions
from chat_stream import stream_chat
from store import SESSIONS, user_for as _user_for

load_dotenv()
BASE = Path(__file__).resolve().parent
SITE = BASE.parent / "site"

app = FastAPI(title="WormGPT (clean rebuild)")
app.include_router(platform_api.router)
# OpenAI-compatible endpoint used by the Models playground; the UI tries
# /api/v1/... first and falls back to /v1/...
app.include_router(completions.router)
app.include_router(completions.router, prefix="/api")


@app.get("/api/public-config")
async def public_config():
    # Test site key: frontend skips Turnstile when it matches /^[123]x0{10,}/
    return {"turnstileSiteKey": "1x00000000000000000000AA"}


@app.post("/api/login")
async def login(req: Request):
    body = await req.json()
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return JSONResponse({"error": "Username and password are required."}, 400)
    token = secrets.token_urlsafe(24)
    user = {"id": hashlib.sha1(username.encode()).hexdigest()[:12],
            "username": username, "email": username if "@" in username else ""}
    license_ = {"key": "CLEAN-REBUILD", "type": "lifetime", "credits": -1,
                "expires": None}
    SESSIONS[token] = {"user": user, "license": license_}
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
    return {"success": True, "status": "ok", "provider": "nvidia",
            "hasKey": nv.has_key()}


@app.get("/api/provider-status")
async def provider_status():
    return {"provider": "nvidia", "model": nv.resolve_model("wormgpt-v6"),
            **(await nv.check_access())}


@app.get("/api/models")
async def models():
    out = []
    for alias, real in nv.MODEL_ALIASES.items():
        out.append({"id": alias, "name": alias, "provider": "NVIDIA NIM",
                    "upstream": real, "status": "operational"})
    return {"object": "list", "data": out}


@app.post("/api/chat-proxy")
async def chat_proxy(req: Request, authorization: str = Header(default="")):
    s = _user_for(authorization.replace("Bearer ", "").strip())
    if not s:
        return JSONResponse({"error": "Authentication token is required."}, 401)
    body = await req.json()
    return StreamingResponse(stream_chat(body), media_type="text/event-stream")



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
    return {"success": True}


from fastapi.responses import FileResponse


@app.get("/{path:path}")
async def spa(path: str):
    target = (SITE / path).resolve()
    if path and str(target).startswith(str(SITE)) and target.is_file():
        return FileResponse(str(target))
    return FileResponse(str(SITE / "index.html"))
