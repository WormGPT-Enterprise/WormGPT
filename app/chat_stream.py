import json
import httpx
import nvidia_client as nv

SSE = "text/event-stream"

def sse(obj):
    return json.dumps(obj) + "\n\n"

def _emit(t, payload):
    return sse({"type": t, "payload": payload})

async def stream_chat(body):
    alias = body.get("model", "wormgpt-v6")
    model = nv.resolve_model(alias)
    messages = nv.with_identity(body.get("messages", []), alias)
    if not nv.has_key():
        yield _emit("status", "NVIDIA_API_KEY is not set on the server.")
        yield _emit("content", "[no key] Set NVIDIA_API_KEY in .env to enable chat.")
        return
    payload = {"model": model, "messages": messages, "stream": True,
               "temperature": 0.7, "max_tokens": body.get("max_tokens", 4096)}
    # The UI sends isThinkingEnabled, but always true for the v6 line. Disable
    # thinking unless the client explicitly asks for it: Nemotron otherwise
    # spends the whole token budget on reasoning_content and returns no answer.
    if not body.get("isThinkingEnabled"):
        payload["chat_template_kwargs"] = {"thinking": False}
    headers = {"Authorization": "Bearer " + nv.API_KEY,
               "Accept": "text/event-stream"}
    async with httpx.AsyncClient(timeout=None) as c:
        async with c.stream("POST", nv.BASE_URL + "/chat/completions",
                            json=payload, headers=headers) as r:
            if r.status_code != 200:
                txt = await r.aread()
                yield _emit("content", "upstream error: " + txt.decode()[:300])
                return
            async for line in r.aiter_lines():
                if not line or not line.startswith(chr(100)+chr(97)+chr(116)+chr(97)):
                    continue
                chunk = line.split(chr(58)+chr(32), 1)[-1]
                if chunk.strip() == chr(91)+chr(68)+chr(79)+chr(78)+chr(69)+chr(93):
                    continue
                try:
                    obj = json.loads(chunk)
                except Exception:
                    continue
                delta = (obj.get(chr(99)+chr(104)+chr(111)+chr(105)+chr(99)+chr(101)+chr(115)) or [{}])[0]
                piece = (delta.get(chr(100)+chr(101)+chr(108)+chr(116)+chr(97)) or {}).get(chr(99)+chr(111)+chr(110)+chr(116)+chr(101)+chr(110)+chr(116))
                if piece:
                    yield _emit(chr(99)+chr(111)+chr(110)+chr(116)+chr(101)+chr(110)+chr(116), piece)
