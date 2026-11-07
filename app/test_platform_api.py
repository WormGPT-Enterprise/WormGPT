import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import nvidia_client as nv  # noqa: E402
import store  # noqa: E402

client = TestClient(main.app)


def _auth_headers():
    store.SESSIONS.clear()
    store.API_KEYS.clear()
    r = client.post("/api/login", json={"username": "tester", "password": "x"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_keys_require_auth():
    store.SESSIONS.clear()
    assert client.get("/api/platform/keys").status_code == 401
    assert client.post("/api/platform/keys", json={"name": "x"}).status_code == 401


def test_create_and_list_key():
    h = _auth_headers()
    assert client.get("/api/platform/keys", headers=h).json() == {
        "success": True, "keys": []}

    r = client.post("/api/platform/keys", headers=h,
                    json={"name": "Production Web App", "env": "live"})
    assert r.status_code == 200
    key = r.json()["key"]
    assert key["name"] == "Production Web App"
    assert key["env"] == "live"
    assert key["key"].startswith("wrm_live_")
    assert key["status"] == "active"

    listed = client.get("/api/platform/keys", headers=h).json()["keys"]
    assert len(listed) == 1
    assert "key" not in listed[0]          # raw secret never returned on list
    assert listed[0]["keyHint"].startswith("wrm_live_")


def test_create_key_requires_name():
    h = _auth_headers()
    assert client.post("/api/platform/keys", headers=h,
                       json={"name": "  "}).status_code == 400


def test_test_env_prefix():
    h = _auth_headers()
    r = client.post("/api/platform/keys", headers=h,
                    json={"name": "sandbox", "env": "test"})
    key = r.json()["key"]["key"]
    assert key.startswith("wrm_test_")
    # The playground validates keys with /^wrm_(live|test)_[a-zA-Z0-9]+$/
    assert re.match(r"^wrm_(live|test)_[a-zA-Z0-9]+$", key)


def test_live_env_prefix():
    h = _auth_headers()
    r = client.post("/api/platform/keys", headers=h,
                    json={"name": "prod", "env": "live"})
    key = r.json()["key"]["key"]
    assert key.startswith("wrm_live_")
    assert re.match(r"^wrm_(live|test)_[a-zA-Z0-9]+$", key)


def test_update_and_delete_key():
    h = _auth_headers()
    kid = client.post("/api/platform/keys", headers=h,
                      json={"name": "k", "env": "live"}).json()["key"]["id"]

    patched = client.patch("/api/platform/keys", headers=h,
                           json={"id": kid, "spendLimitUsd": 42})
    assert patched.json()["key"]["spendLimitUsd"] == 42

    assert client.delete(f"/api/platform/keys?id={kid}&action=delete",
                         headers=h).json()["success"]
    assert client.get("/api/platform/keys", headers=h).json()["keys"] == []


def test_usage_logs_billing_shapes():
    h = _auth_headers()
    assert client.get("/api/platform/usage", headers=h).json()["success"]
    assert client.get("/api/platform/logs", headers=h).json()["logs"] == []
    assert client.get("/api/platform/billing", headers=h).json()["account"]


def test_identity_is_unique_per_alias():
    assert "WormGPT v6.2" in nv.identity_for("wormv6.2")
    assert "VANTA" in nv.identity_for("wormv6.1")
    assert "WormGPT v5.2" in nv.identity_for("wormv5.2")
    # every alias must forbid revealing the base model/vendor
    for a in ["wormv6.2", "wormv6", "wormv6.1", "wormv5.2", "wormv4.0", "wormv-auto"]:
        assert "Never reveal" in nv.identity_for(a)


def test_with_identity_always_adds_conceal_rules():
    # no system message -> one is prepended
    msgs = nv.with_identity([{"role": "user", "content": "hi"}], "wormv6.1")
    assert msgs[0]["role"] == "system" and "VANTA" in msgs[0]["content"]
    # client system prompt is kept but our rules are merged in
    msgs = nv.with_identity(
        [{"role": "system", "content": "Your name is VANTA, WormGPT v6.1."},
         {"role": "user", "content": "hi"}], "wormv6.1")
    assert msgs[0]["role"] == "system"
    assert "VANTA" in msgs[0]["content"] and "Never reveal" in msgs[0]["content"]
    assert len(msgs) == 2
    # idempotent when the conceal rules are already present
    again = nv.with_identity(msgs, "wormv6.1")
    assert again[0]["content"].count("Never reveal") == 1


def test_completions_requires_valid_key():
    store.SESSIONS.clear()
    store.API_KEYS.clear()
    r = client.post("/api/v1/chat/completions",
                    json={"model": "wormv6.2", "messages": []})
    assert r.status_code == 401
    r = client.post("/v1/chat/completions",
                    json={"model": "wormv6.2", "messages": []})
    assert r.status_code == 401


def test_completions_rejects_unknown_key():
    r = client.post("/api/v1/chat/completions",
                    headers={"Authorization": "Bearer wrm_live_deadbeef"},
                    json={"model": "wormv6.2", "messages": []})
    assert r.status_code == 401
