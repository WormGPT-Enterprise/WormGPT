"""API-key / usage / logs / billing endpoints the cloned frontend expects.

The frontend calls these under ``/api/platform/*``; without them the
"Create Secret Key" button silently fails.
"""
import datetime
import secrets
import time

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

import store
from store import API_KEYS, REQUEST_LOGS, register_key, token_from_header, user_for

router = APIRouter(prefix="/api/platform", tags=["platform"])

PRICE_PER_1K = 0.0002

# The analytics chart renders one bucket per requested day; an unbounded
# `days` built 100k buckets (~10 MB, ~2s) and 1e9 crashed the worker.
MAX_USAGE_DAYS = 90
# /logs accepts a limit; keep it in step with the stored cap.
MAX_LOG_ROWS = store.MAX_LOG_ROWS


def _parse_spend_limit(value):
    """Return a non-negative float, or None when the client sends no limit.

    Raises ValueError for anything that is not a finite number: a string like
    "abc" used to be stored verbatim and then blew up every later chat request
    with a 500 when ``float()`` ran inside the limit check.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("spendLimitUsd must be a number.")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError("spendLimitUsd must be a finite number.")
    if number < 0:
        raise ValueError("spendLimitUsd cannot be negative.")
    return number


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
    """Key records for listing: never expose the raw secret or its hash."""
    return {k: v for k, v in record.items() if k not in ("key", "keyHash")}


def _new_key_record(name: str, env: str, spend_limit):
    prefix = "wrm_live" if env == "live" else "wrm_test"
    # The UI validates keys with /^wrm_(live|test)_[a-zA-Z0-9]+$/, so the body
    # must stay alphanumeric (token_urlsafe would add "-"/"_" and fail it).
    secret = f"{prefix}_{secrets.token_hex(24)}"
    return {
        "id": secrets.token_hex(8),
        "name": name,
        "env": "live" if env == "live" else "test",
        # Only the hash is stored; the raw secret exists solely in the POST
        # response. Auth looks the hash up in the index (O(1), no scanning).
        "key": secret,
        "keyHash": store.key_hash(secret),
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
    try:
        spend_limit = _parse_spend_limit(body.get("spendLimitUsd"))
    except (TypeError, ValueError):
        return JSONResponse(
            {"error": "spendLimitUsd must be a non-negative number."}, 400)
    record = _new_key_record(name, body.get("env", "live"), spend_limit)
    API_KEYS.setdefault(_uid(user), []).insert(0, record)
    register_key(_uid(user), record)
    return {"success": True, "key": record, "message": "API key generated successfully."}


@router.patch("/keys")
async def update_key(req: Request, authorization: str = Header(default="")):
    user, err = _auth(authorization)
    if err:
        return err
    body = await req.json()
    if "spendLimitUsd" in body:
        try:
            spend_limit = _parse_spend_limit(body.get("spendLimitUsd"))
        except (TypeError, ValueError):
            return JSONResponse(
                {"error": "spendLimitUsd must be a non-negative number."}, 400)
    else:
        spend_limit = None
    for record in API_KEYS.get(_uid(user), []):
        if record["id"] == body.get("id"):
            if "spendLimitUsd" in body:
                record["spendLimitUsd"] = spend_limit
            return {"success": True, "key": _public(record)}
    return JSONResponse({"error": "API key not found."}, 404)


@router.delete("/keys")
async def delete_key(id: str = "", action: str = "delete",
                     authorization: str = Header(default="")):
    user, err = _auth(authorization)
    if err:
        return err
    keys = API_KEYS.get(_uid(user), [])
    remaining = [k for k in keys if k["id"] != id]
    if len(remaining) == len(keys):
        return JSONResponse({"error": "API key not found."}, 404)
    for k in keys:
        if k["id"] == id:
            store.KEY_INDEX.pop(k.get("keyHash", ""), None)
    API_KEYS[_uid(user)] = remaining
    return {"success": True}


@router.get("/usage")
async def usage(days: int = Query(default=14, ge=1, le=MAX_USAGE_DAYS),
                authorization: str = Header(default="")):
    user, err = _auth(authorization)
    if err:
        return err
    logs = REQUEST_LOGS.get(_uid(user), [])
    total_tokens = sum(l.get("totalTokens", 0) for l in logs)
    summary = {
        "totalRequests": len(logs),
        "totalTokens": total_tokens,
        "totalCost": round(total_tokens / 1000 * PRICE_PER_1K, 4),
        "balance": 25.0,
    }
    # The analytics chart reads one bucket per day, newest last.
    buckets: dict[str, dict] = {}
    for offset in range(days - 1, -1, -1):
        day = datetime.date.today() - datetime.timedelta(days=offset)
        buckets[day.isoformat()] = {
            "date": day.isoformat(),
            "formattedDate": day.strftime("%b %d"),
            "requests": 0, "promptTokens": 0, "completionTokens": 0,
            "totalTokens": 0, "cost": 0.0, "errors": 0,
        }
    for log in logs:
        day = datetime.date.fromtimestamp(log.get("timestamp", 0) / 1000).isoformat()
        bucket = buckets.get(day)
        if bucket is None:
            continue
        bucket["requests"] += 1
        bucket["promptTokens"] += log.get("promptTokens", 0)
        bucket["completionTokens"] += log.get("completionTokens", 0)
        bucket["totalTokens"] += log.get("totalTokens", 0)
        bucket["cost"] = round(bucket["totalTokens"] / 1000 * PRICE_PER_1K, 4)
        if log.get("statusCode", 200) >= 400:
            bucket["errors"] += 1
    return {"success": True, "summary": summary, "dailyUsage": list(buckets.values())}


@router.get("/logs")
async def logs(limit: int = Query(default=50, ge=1, le=MAX_LOG_ROWS),
               authorization: str = Header(default="")):
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
