"""OpenAI-compatible /v1/chat/completions used by the Models playground."""
import json
import math
import secrets
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

import nvidia_client as nv
from store import API_KEYS, REQUEST_LOGS, user_for

router = APIRouter(tags=["openai-compat"])

PRICE_PER_1K = 0.0002


def _key_record(key):
    """Return (user_id, key record) for a platform key, else (None, None)."""
    for uid, records in API_KEYS.items():
        for r in records:
            if r.get("key") == key:
                return uid, r
    return None, None


def _bearer(req):
    h = req.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return req.headers.get("x-api-key", "").strip()


def _resolve_key(req):
    """Accept either a platform API key or a logged-in session token."""
    raw = _bearer(req)
    if not raw:
        return None, None, None
    uid, record = _key_record(raw)
    if uid:
        return uid, "api_key", record
    s = user_for(raw)
    if s:
        return s["user"]["id"], "session", None
    return None, None, None


def _log_request(uid, key_record, alias, status, usage, duration_ms):
    """Append a log row shaped exactly like the Request Logs table expects."""
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion))
    if key_record is not None:
        key_record["totalRequests"] = key_record.get("totalRequests", 0) + 1
        key_record["lastUsedAt"] = int(time.time() * 1000)
        key_record["totalSpentUsd"] = round(
            key_record.get("totalSpentUsd", 0.0) + total / 1000 * PRICE_PER_1K, 6)
    logs = REQUEST_LOGS.setdefault(uid, [])
    logs.insert(0, {
        "id": "req_" + secrets.token_hex(6),
        "timestamp": int(time.time() * 1000),
        "statusCode": status,
        "model": alias,
        "promptTokens": prompt,
        "completionTokens": completion,
        "totalTokens": total,
        "durationMs": duration_ms,
        "keyName": (key_record or {}).get("name") or "Session",
    })


def _over_limit(key_record):
    limit = (key_record or {}).get("spendLimitUsd")
    if limit is None:
        return False
    return (key_record.get("totalSpentUsd") or 0.0) >= float(limit)


def _mask_model(text, alias, real):
    """Hide the real NIM model id in responses so it never leaks to clients."""
    if real == alias:
        return text
    try:
        obj = json.loads(text)
    except Exception:
        return text
    if isinstance(obj, dict):
        if obj.get("model") == real:
            obj["model"] = alias
        _sanitize(obj)
        return json.dumps(obj)
    return text


def _mask_sse(line, alias, real):
    if not line.startswith("data:"):
        return line
    return "data: " + _mask_model(line[5:].strip(), alias, real)


def _sanitize(data):
    """Drop the upstream chain-of-thought so it cannot leak the base model.

    Reasoning models return the whole thought process in `reasoning_content`;
    even with conceal rules that text can name the vendor. The clients read
    only `content`, so removing the field is safe.
    """
    if isinstance(data, dict):
        for choice in data.get("choices", []) or []:
            if isinstance(choice, dict):
                for field in ("message", "delta"):
                    part = choice.get(field)
                    if isinstance(part, dict):
                        part.pop("reasoning_content", None)
    return data


@router.post("/v1/chat/completions")
async def chat_completions(req: Request):
    owner, _how, key_record = _resolve_key(req)
    if not owner:
        return JSONResponse({"error": {"message": "Invalid API key. Create one in the API Platform, then pass it as a Bearer token."}}, 401)
    if _over_limit(key_record):
        return JSONResponse({"error": {"message": "Spend limit reached for this API key. Raise the limit in the API Platform to continue."}}, 429)
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
    started = time.monotonic()
    if payload["stream"]:
        prompt_chars = sum(len(str(m.get("content") or "")) for m in messages)
        headers["Accept"] = "text/event-stream"
        client = httpx.AsyncClient(timeout=None)
        up = await client.send(
            client.build_request("POST", nv.BASE_URL + "/chat/completions",
                                 json=payload, headers=headers), stream=True)
        if up.status_code != 200:
            txt = await up.aread()
            await up.aclose(); await client.aclose()
            _log_request(owner, key_record, alias, up.status_code, {}, 0)
            return JSONResponse({"error": {"message": txt.decode()[:400]}}, up.status_code)

        async def gen():
            # Upstream only reports usage when the client asks for it; the
            # playground does not, so count the streamed text and estimate.
            usage = {}
            chars = 0
            try:
                async for line in up.aiter_lines():
                    if not line:
                        continue
                    chunk = _mask_sse(line, alias, model)
                    if chunk.startswith("data:"):
                        try:
                            obj = json.loads(chunk[5:].strip())
                            if isinstance(obj, dict):
                                if obj.get("usage"):
                                    usage = obj["usage"]
                                for choice in obj.get("choices", []) or []:
                                    part = choice.get("delta") or choice.get("message") or {}
                                    chars += len(part.get("content") or "")
                        except Exception:
                            pass
                    yield chunk + "\n\n"
            finally:
                await up.aclose(); await client.aclose()
                if not usage.get("total_tokens"):
                    prompt = math.ceil(prompt_chars / 4)
                    completion = math.ceil(chars / 4)
                    usage = {"prompt_tokens": prompt,
                             "completion_tokens": completion,
                             "total_tokens": prompt + completion}
                _log_request(owner, key_record, alias, 200, usage,
                             int((time.monotonic() - started) * 1000))

        return StreamingResponse(gen(), media_type="text/event-stream")
    async with httpx.AsyncClient(timeout=None) as c:
        r = await c.post(nv.BASE_URL + "/chat/completions", json=payload, headers=headers)
    data = r.json()
    if isinstance(data, dict) and data.get("model") == model:
        data["model"] = alias
    data = _sanitize(data)
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    _log_request(owner, key_record, alias, r.status_code, usage,
                 int((time.monotonic() - started) * 1000))
    return JSONResponse(data, r.status_code)
