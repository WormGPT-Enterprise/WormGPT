"""API-key / usage / logs / billing endpoints the cloned frontend expects.

The frontend calls these under ``/api/platform/*``; without them the
"Create Secret Key" button silently fails.
"""
import secrets
import time

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from store import API_KEYS, REQUEST_LOGS, token_from_header, user_for

router = APIRouter(prefix="/api/platform", tags=["platform"])


def _auth(authorization: str):
    session = user_for(token_from_header(authorization))
    if not session:
        return None, JSONResponse({"error": "Authentication token is required."}, 401)
    return session["user"], None


def _uid(user: dict) -> str:
    return user["id"]


def _mask(key: str) -> str:
    # Keep the full "wrm_live_"/"wrm_test_" prefix, hide the secret body.
    if not key:
        return "\u2022\u2022\u2022\u2022"
    cut = key.find("_", key.find("_") + 1) + 1 if key.count("_") >= 2 else 8
    return f"{key[:cut]}\u2022\u2022\u2022\u2022"


def _public(record: dict) -> dict:
    """Key records for listing: never expose the raw secret."""
    return {k: v for k, v in record.items() if k != "key"}


def _new_key_record(name: str, env: str, spend_limit):
    prefix = "wrm_live" if env == "live" else "wrm_test"
    # The UI validates keys with /^wrm_(live|test)_[a-zA-Z0-9]+$/, so the body
    # must stay alphanumeric (token_urlsafe would add "-"/"_" and fail it).
    secret = f"{prefix}_{secrets.token_hex(24)}"
    return {
        "id": secrets.token_hex(8),
        "name": name,
        "env": env,
        "key": secret,
        "keyHint": _mask(secret),
        "status": "active",
        "createdAt": int(time.time() * 1000),
        "lastUsedAt": None,
        "totalRequests": 0,
        "totalSpentUsd": 0.0,
        "spendLimitUsd": spend_limit,
        "rateLimitRpm": 600,
    }


@router.get("/keys")
async def list_keys(authorization: str = Header(default="")):
    user, err = _auth(authorization)
    if err:
        return err
    return {"success": True, "keys": [_public(k) for k in API_KEYS.get(_uid(user), [])]}


@router.post("/keys")
async def create_key(req: Request, authorization: str = Header(default="")):
    user, err = _auth(authorization)
    if err:
        return err
    body = await req.json()
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "Key name is required."}, 400)
    record = _new_key_record(name, body.get("env", "live"), body.get("spendLimitUsd"))
    API_KEYS.setdefault(_uid(user), []).insert(0, record)
    return {"success": True, "key": record, "message": "API key generated successfully."}


@router.patch("/keys")
async def update_key(req: Request, authorization: str = Header(default="")):
    user, err = _auth(authorization)
    if err:
        return err
    body = await req.json()
    for record in API_KEYS.get(_uid(user), []):
        if record["id"] == body.get("id"):
            record["spendLimitUsd"] = body.get("spendLimitUsd")
            return {"success": True, "key": _public(record)}
    return JSONResponse({"error": "API key not found."}, 404)


@router.delete("/keys")
async def delete_key(id: str = "", action: str = "delete",
                     authorization: str = Header(default="")):
    user, err = _auth(authorization)
    if err:
        return err
    keys = API_KEYS.get(_uid(user), [])
    API_KEYS[_uid(user)] = [k for k in keys if k["id"] != id]
    return {"success": True}


@router.get("/usage")
async def usage(days: int = 14, authorization: str = Header(default="")):
    user, err = _auth(authorization)
    if err:
        return err
    logs = REQUEST_LOGS.get(_uid(user), [])
    summary = {
        "totalRequests": len(logs),
        "totalTokens": sum(l["totalTokens"] for l in logs),
        "totalCost": round(sum(l["totalTokens"] for l in logs) / 1000 * 0.0002, 4),
        "balance": 25.0,
    }
    return {"success": True, "summary": summary, "dailyUsage": []}


@router.get("/logs")
async def logs(limit: int = 50, authorization: str = Header(default="")):
    user, err = _auth(authorization)
    if err:
        return err
    return {"success": True, "logs": REQUEST_LOGS.get(_uid(user), [])[:limit]}


@router.get("/billing")
async def billing(authorization: str = Header(default="")):
    user, err = _auth(authorization)
    if err:
        return err
    return {
        "success": True,
        "account": {"balance": 25.0, "totalSpent": 0.0,
                    "lastPaymentAt": None, "rpmLimit": 600},
        "ledger": [],
        "payments": [],
    }
