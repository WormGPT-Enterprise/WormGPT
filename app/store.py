"""Shared in-memory state for the demo backend (not persisted)."""

SESSIONS: dict[str, dict] = {}          # token -> {"user":..., "license":...}
API_KEYS: dict[str, list[dict]] = {}    # user id -> list of key records
REQUEST_LOGS: dict[str, list[dict]] = {}  # user id -> list of request log records


def user_for(token: str | None):
    return SESSIONS.get(token or "")


def token_from_header(authorization: str | None) -> str:
    return (authorization or "").replace("Bearer ", "").strip()
