"""Shared in-memory state for the demo backend (not persisted)."""
import hashlib
import hmac
import secrets
import time

# Bounds the in-memory request log so a long-lived worker cannot grow without
# limit. Shared by the chat completions logger and the platform log endpoint.
MAX_LOG_ROWS = 1000

# Sessions used to live until the process restarted; a stolen token stayed
# valid forever. 12h matches the frontend session cache window.
SESSION_TTL = 12 * 3600

SESSIONS: dict[str, dict] = {}          # token -> {"user":..., "license":...}
API_KEYS: dict[str, list[dict]] = {}    # user id -> list of key records
KEY_INDEX: dict[str, tuple[str, dict]] = {}  # key hash -> (user id, record)
REQUEST_LOGS: dict[str, list[dict]] = {}  # user id -> list of request log records
UPLOADS: dict[str, list[dict]] = {}       # user id -> uploaded file records
ADS: list[dict] = []                       # submitted advertisements

# There is no user table; credentials are keyed by username so a repeat login
# must present the same password. The first login for a new name bootstraps it.
CREDENTIALS: dict[str, str] = {}          # username -> "pbkdf2$iterations$salt$hash"

PBKDF2_ITERATIONS = 120_000


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(),
                                 PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(username: str, password: str) -> bool | None:
    """True/False when a credential exists, None when the name is unknown."""
    stored = CREDENTIALS.get(username)
    if not stored:
        return None
    try:
        _, iterations, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(),
                                     int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


def set_password(username: str, password: str) -> None:
    CREDENTIALS[username] = hash_password(password)


# The platform advertises rateLimitRpm per key; this is the bucket that makes
# the promise real. key id -> (tokens, last refill timestamp).
RATE_BUCKETS: dict[str, tuple[float, float]] = {}


def allow_request(bucket_id: str, rpm: int) -> bool:
    """Token bucket with a burst of `rpm` and a refill of rpm/60 per second."""
    if rpm <= 0:
        return True
    now = time.time()
    tokens, last = RATE_BUCKETS.get(bucket_id, (float(rpm), now))
    tokens = min(float(rpm), tokens + (now - last) * (rpm / 60.0))
    if tokens < 1.0:
        RATE_BUCKETS[bucket_id] = (tokens, now)
        return False
    RATE_BUCKETS[bucket_id] = (tokens - 1.0, now)
    return True


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def register_key(uid: str, record: dict) -> None:
    """Index a key by hash so auth is O(1) instead of scanning every key."""
    KEY_INDEX[record["keyHash"]] = (uid, record)


def find_key(key: str):
    """Return (user id, record) for a key, verified in constant time."""
    if not key:
        return None, None
    digest = key_hash(key)
    uid, record = KEY_INDEX.get(digest, (None, None))
    if record is None:
        return None, None
    if record not in API_KEYS.get(uid, []):
        KEY_INDEX.pop(digest, None)
        return None, None
    if not hmac.compare_digest(record.get("keyHash", ""), digest):
        return None, None
    return uid, record


def session_create(user: dict, license_: dict) -> str:
    token = secrets.token_urlsafe(24)
    SESSIONS[token] = {"user": user, "license": license_,
                       "expiresAt": time.time() + SESSION_TTL}
    return token


def prune_sessions() -> None:
    now = time.time()
    for token in [t for t, s in SESSIONS.items() if s.get("expiresAt", 0) < now]:
        SESSIONS.pop(token, None)


def user_for(token: str | None):
    record = SESSIONS.get(token or "")
    if not record:
        return None
    expires = record.get("expiresAt")
    # A record without expiresAt is treated as non-expiring (tests and older
    # code insert session dicts directly).
    if expires is not None and expires < time.time():
        SESSIONS.pop(token, None)
        return None
    return record


def token_from_header(authorization: str | None) -> str:
    return (authorization or "").replace("Bearer ", "").strip()
