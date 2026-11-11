"""Regression tests for the platform/chat hardening pass.

Each test pins a bug that was reproduced against the running app before the fix.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import completions  # noqa: E402
import main  # noqa: E402
import platform_api  # noqa: E402
import store  # noqa: E402

client = TestClient(main.app, raise_server_exceptions=False)


def _auth():
    store.SESSIONS.clear()
    store.API_KEYS.clear()
    store.REQUEST_LOGS.clear()
    store.ADS.clear()
    token = client.post("/api/login",
                        json={"username": "tester", "password": "x"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _make_key(headers, **body):
    payload = {"name": "k", "env": "live"}
    payload.update(body)
    return client.post("/api/platform/keys", headers=headers, json=payload).json()["key"]


# --- P1-1: spendLimitUsd validation ----------------------------------------

@pytest.mark.parametrize("bad", ["abc", {"a": 1}, [1], True, -5])
def test_create_key_rejects_bad_spend_limit(bad):
    h = _auth()
    r = client.post("/api/platform/keys", headers=h,
                    json={"name": "k", "spendLimitUsd": bad})
    assert r.status_code == 400
    assert "spendLimitUsd" in r.json()["error"]


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_parse_spend_limit_rejects_non_finite(bad):
    # inf/nan cannot travel through JSON, so this is exercised directly.
    with pytest.raises(ValueError):
        platform_api._parse_spend_limit(bad)


def test_create_key_accepts_missing_and_numeric_limit():
    h = _auth()
    assert client.post("/api/platform/keys", headers=h,
                       json={"name": "k"}).status_code == 200
    assert client.post("/api/platform/keys", headers=h,
                       json={"name": "k", "spendLimitUsd": 12.5}).json()[
        "key"]["spendLimitUsd"] == 12.5
    assert client.post("/api/platform/keys", headers=h,
                       json={"name": "k", "spendLimitUsd": ""}).json()[
        "key"]["spendLimitUsd"] is None


def test_over_limit_tolerates_non_numeric_limit():
    """A stored non-numeric limit must not raise inside the request path."""
    assert completions._over_limit({"spendLimitUsd": "abc", "totalSpentUsd": 1.0}) is False
    assert completions._over_limit({"spendLimitUsd": {"a": 1}}) is False
    assert completions._over_limit(None) is False


def test_patch_key_rejects_bad_limit():
    h = _auth()
    kid = _make_key(h)["id"]
    assert client.patch("/api/platform/keys", headers=h,
                        json={"id": kid, "spendLimitUsd": "oops"}).status_code == 400
    assert client.patch("/api/platform/keys", headers=h,
                        json={"id": kid, "spendLimitUsd": -1}).status_code == 400


def test_patch_without_limit_keeps_existing_value():
    h = _auth()
    kid = _make_key(h, spendLimitUsd=9)["id"]
    r = client.patch("/api/platform/keys", headers=h, json={"id": kid, "name": "renamed"})
    assert r.json()["key"]["spendLimitUsd"] == 9


# --- P1-2 / P2-10: bounded usage and logs ----------------------------------

def test_usage_days_is_bounded():
    h = _auth()
    assert client.get("/api/platform/usage?days=100000", headers=h).status_code == 422
    assert client.get("/api/platform/usage?days=1000000000", headers=h).status_code == 422
    assert client.get("/api/platform/usage?days=0", headers=h).status_code == 422
    assert client.get("/api/platform/usage?days=-3", headers=h).status_code == 422
    assert len(client.get("/api/platform/usage?days=90", headers=h).json()["dailyUsage"]) == 90
    assert len(client.get("/api/platform/usage", headers=h).json()["dailyUsage"]) == 14


def test_logs_limit_is_bounded_and_never_negative_slices():
    h = _auth()
    assert client.get("/api/platform/logs?limit=-1", headers=h).status_code == 422
    assert client.get("/api/platform/logs?limit=0", headers=h).status_code == 422
    assert client.get("/api/platform/logs?limit=1000000", headers=h).status_code == 422
    assert client.get("/api/platform/logs?limit=50", headers=h).status_code == 200


def test_request_logs_are_capped():
    store.REQUEST_LOGS.clear()
    for i in range(store.MAX_LOG_ROWS + 250):
        completions._log_request("u", None, "wormv6", 200,
                                 {"total_tokens": 1}, 0)
    assert len(store.REQUEST_LOGS["u"]) == store.MAX_LOG_ROWS


# --- P2-1: delete reports a missing key -----------------------------------

def test_delete_missing_key_returns_404():
    h = _auth()
    assert client.delete("/api/platform/keys?id=nope", headers=h).status_code == 404
    kid = _make_key(h)["id"]
    assert client.delete(f"/api/platform/keys?id={kid}", headers=h).status_code == 200


# --- P1-4: advertisement auth + isolation ---------------------------------

def test_advertisement_post_requires_auth():
    store.SESSIONS.clear()
    store.ADS.clear()
    r = client.post("/api/advertisement", json={"productName": "Spam"})
    assert r.status_code == 401
    assert store.ADS == []


def test_advertisements_are_not_shared_between_users():
    store.SESSIONS.clear()
    store.ADS.clear()
    alice = client.post("/api/login", json={"username": "alice", "password": "x"}).json()["token"]
    bob = client.post("/api/login", json={"username": "bob", "password": "x"}).json()["token"]
    client.post("/api/advertisement",
                headers={"Authorization": "Bearer " + bob},
                json={"productName": "BOB", "contactInfo": "bob@private.com"})
    seen = client.get("/api/advertisement",
                      headers={"Authorization": "Bearer " + alice}).json()["ads"]
    assert seen == []
    mine = client.get("/api/advertisement",
                      headers={"Authorization": "Bearer " + bob}).json()["ads"]
    assert [a["productName"] for a in mine] == ["BOB"]


# --- P1-5 / P1-6: auth and JSON errors ------------------------------------

def test_chats_wipe_requires_auth():
    store.SESSIONS.clear()
    assert client.post("/api/chats-wipe").status_code == 401
    assert client.post("/api/chats-wipe", headers=_auth()).status_code == 200


def test_malformed_json_returns_json_not_html():
    h = _auth()
    r = client.post("/api/chat-proxy", headers={**h, "Content-Type": "application/json"},
                    content=b"not json")
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("application/json")
    assert "error" in r.json()


def test_chat_proxy_rejects_non_list_messages():
    h = _auth()
    r = client.post("/api/chat-proxy", headers=h,
                    json={"model": "wormv6", "messages": "string"})
    assert r.status_code == 400
    assert r.json()["error"]


def test_unknown_api_path_returns_json_404_not_spa_html():
    r = client.get("/api/platform/admin")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert "text/html" not in r.headers["content-type"]


def test_unknown_model_is_400_not_500():
    h = _auth()
    key = _make_key(h)["key"]
    r = client.post("/api/v1/chat/completions",
                    headers={"Authorization": "Bearer " + key},
                    json={"model": "totally-made-up",
                          "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 400
    assert "Unknown model" in r.json()["error"]["message"]


def test_upstream_failure_is_502_not_500(monkeypatch):
    h = _auth()
    key = _make_key(h)["key"]
    monkeypatch.setattr(completions.nv, "BASE_URL", "http://127.0.0.1:1/v1")
    r = client.post("/api/v1/chat/completions",
                    headers={"Authorization": "Bearer " + key},
                    json={"model": "wormv6", "messages": [{"role": "user", "content": "hi"}],
                          "stream": False})
    assert r.status_code == 502
    assert "unreachable" in r.json()["error"]["message"].lower()


# --- P2-4: stream failures are logged as errors ---------------------------

def test_broken_stream_is_logged_with_error_status():
    store.REQUEST_LOGS.clear()
    completions._log_request("u", None, "wormv6", 502, {}, 12)
    assert store.REQUEST_LOGS["u"][0]["statusCode"] == 502


# --- environment normalisation -------------------------------------------

def test_unknown_env_falls_back_to_test_prefix():
    h = _auth()
    key = _make_key(h, env="weird")["key"]
    assert key.startswith("wrm_test_")


# --- P0: runner must not leak the server's secrets to child code -----------

def test_runner_child_does_not_see_server_secrets(monkeypatch):
    import runner
    monkeypatch.setenv("NVIDIA_API_KEY", "super-secret-value")
    monkeypatch.setenv("SOME_TOKEN", "abc")
    env = runner._child_env()
    assert "NVIDIA_API_KEY" not in env
    assert "SOME_TOKEN" not in env
    assert env.get("PATH")  # interpreters stay usable


def test_runner_still_executes_code_with_scrubbed_env():
    import runner
    r = runner.run_files([{"name": "main.py", "content": "print(2 + 2)"}])
    assert r["ok"] and r["stdout"].strip() == "4"


def test_runner_applies_memory_limit():
    import runner
    r = runner.run_files([{"name": "main.py", "content":
                           "import resource;print(resource.getrlimit(resource.RLIMIT_AS)[0] > 0)"}])
    assert r["stdout"].strip() == "True"


# --- P1: password verification --------------------------------------------

def test_login_bootstraps_then_requires_the_same_password():
    store.SESSIONS.clear()
    store.CREDENTIALS.clear()
    first = client.post("/api/login", json={"username": "pw-user", "password": "s3cret"})
    assert first.status_code == 200
    assert client.post("/api/login",
                       json={"username": "pw-user", "password": "nope"}).status_code == 401
    assert client.post("/api/login",
                       json={"username": "pw-user", "password": "s3cret"}).status_code == 200


def test_stored_credential_is_hashed_not_plaintext():
    store.CREDENTIALS.clear()
    client.post("/api/login", json={"username": "hash-user", "password": "topsecret"})
    stored = store.CREDENTIALS["hash-user"]
    assert "topsecret" not in stored
    assert stored.startswith("pbkdf2$")


def test_verify_password_unknown_user_returns_none():
    store.CREDENTIALS.clear()
    assert store.verify_password("nobody", "x") is None


# --- P2: session TTL ------------------------------------------------------

def test_expired_session_is_rejected():
    import time as _time
    store.SESSIONS.clear()
    token = client.post("/api/login",
                        json={"username": "ttl-user", "password": "p"}).json()["token"]
    assert client.get("/api/session",
                      headers={"Authorization": "Bearer " + token}).status_code == 200
    store.SESSIONS[token]["expiresAt"] = _time.time() - 1
    assert client.get("/api/session",
                      headers={"Authorization": "Bearer " + token}).status_code == 401


def test_session_without_expiry_still_works():
    """Tests and older callers insert session dicts directly."""
    store.SESSIONS.clear()
    store.SESSIONS["legacy"] = {"user": {"id": "u", "username": "l"},
                                "license": {"type": "lifetime"}}
    assert client.get("/api/session",
                      headers={"Authorization": "Bearer legacy"}).status_code == 200


# --- P2: hashed key index and constant-time lookup ------------------------

def test_key_auth_uses_hash_index():
    h = _auth()
    created = client.post("/api/platform/keys", headers=h,
                          json={"name": "Indexed", "env": "live"}).json()["key"]
    record = next(r for recs in store.API_KEYS.values() for r in recs)
    assert "keyHash" in record and record["keyHash"] not in (record["key"],)
    assert record["keyHash"] in store.KEY_INDEX
    listed = client.get("/api/platform/keys", headers=h).json()["keys"][0]
    assert "keyHash" not in listed and "key" not in listed
    uid, found = store.find_key(created["key"])
    assert found is record


def test_deleted_key_leaves_no_index_entry():
    h = _auth()
    created = client.post("/api/platform/keys", headers=h,
                          json={"name": "Gone", "env": "test"}).json()["key"]
    client.delete(f"/api/platform/keys?id={created['id']}", headers=h)
    assert created["keyHash"] not in store.KEY_INDEX
    assert store.find_key(created["key"]) == (None, None)


# --- P2: advertised rate limit is enforced --------------------------------

def test_rate_limit_bucket_blocks_after_burst():
    store.RATE_BUCKETS.clear()
    assert all(store.allow_request("bucket", 3) for _ in range(3))
    assert store.allow_request("bucket", 3) is False


def test_rate_limit_zero_means_unlimited():
    assert store.allow_request("unlimited", 0) is True
