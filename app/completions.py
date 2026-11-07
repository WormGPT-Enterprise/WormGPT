"""OpenAI-compatible /v1/chat/completions used by the Models playground."""
import json
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

import nvidia_client as nv
from store import API_KEYS, REQUEST_LOGS, user_for

router = APIRouter(tags=["openai-compat"])


def _key_owner(key):
    for uid, records in API_KEYS.items():
        for r in records:
            if r.get("key") == key:
                return uid
    return None


def _bearer(req):
    h = req.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return req.headers.get("x-api-key", "").strip()


def _resolve_key(req):
    """Accept either a platform API key or a logged-in session token."""
    raw = _bearer(req)
    if not raw:
        return None, None
    owner = _key_owner(raw)
    if owner:
        return owner, "api_key"
    s = user_for(raw)
    if s:
        return s["user"]["id"], "session"
    return None, None


def _mask_model(text, alias, real):
    """Hide the real NIM model id in responses so it never leaks to clients."""
    if real == alias:
        return text
    try:
        obj = json.loads(text)
    except Exception:
        return text
    if isinstance(obj, dict) and obj.get("model") == real:
        obj["model"] = alias
        return json.dumps(obj)
    return text


def _mask_sse(line, alias, real):
    if not line.startswith("data:"):
        return line
    return "data: " + _mask_model(line[5:].strip(), alias, real)


@router.post("/v1/chat/completions")
async def chat_completions(req: Request):
    owner, _how = _resolve_key(req)
    if not owner:
        return JSONResponse({"error": {"message": "Invalid API key. Create one in the API Platform, then pass it as a Bearer token."}}, 401)
    body = await req.json()
    alias = body.get("model", "wormv-auto")
    model = nv.resolve_model(alias)
    messages = nv.with_identity(body.get("messages", []), alias)
    payload = {"model": model, "messages": messages,
               "temperature": body.get("temperature", 0.7),
               "max_tokens": body.get("max_tokens", 4096),
               "stream": bool(body.get("stream"))}
    if not body.get("isThinkingEnabled"):
        payload["chat_template_kwargs"] = {"thinking": False}
    headers = {"Authorization": "Bearer " + nv.API_KEY}
    if not nv.has_key():
        return JSONResponse({"error": {"message": "Server has no NVIDIA_API_KEY configured."}}, 503)
    if payload["stream"]:
        headers["Accept"] = "text/event-stream"
        client = httpx.AsyncClient(timeout=None)
        up = await client.send(
            client.build_request("POST", nv.BASE_URL + "/chat/completions",
                                 json=payload, headers=headers), stream=True)
        if up.status_code != 200:
            txt = await up.aread()
            await up.aclose(); await client.aclose()
            return JSONResponse({"error": {"message": txt.decode()[:400]}}, up.status_code)

        async def gen():
            try:
                async for line in up.aiter_lines():
                    if line:
                        yield _mask_sse(line, alias, model) + "\n\n"
            finally:
                await up.aclose(); await client.aclose()

        return StreamingResponse(gen(), media_type="text/event-stream")
    async with httpx.AsyncClient(timeout=None) as c:
        r = await c.post(nv.BASE_URL + "/chat/completions", json=payload, headers=headers)
    data = r.json()
    if isinstance(data, dict) and data.get("model") == model:
        data["model"] = alias
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    REQUEST_LOGS.setdefault(owner, []).insert(0, {
        "id": "req_" + str(len(REQUEST_LOGS.get(owner, [])) + 1),
        "model": alias, "status": r.status_code,
        "totalTokens": usage.get("total_tokens", 0),
        "createdAt": int(__import__("time").time() * 1000)})
    return JSONResponse(data, r.status_code)
