import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import completions  # noqa: E402
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


def test_catalog_aliases_map_to_distinct_models():
    # Each catalog entry must be a different engine; descriptions promise
    # different behaviour, so sharing one base model would be a bug.
    aliases = ["wormv6.2", "wormv6", "wormv6.1", "wormv5.2",
               "wormv5.1", "wormv5.0", "wormv4.1", "wormv4.0"]
    real = [nv.resolve_model(a) for a in aliases]
    assert len(set(real)) == len(real)
    assert "nvidia/nemotron-3-ultra-550b-a55b" not in real[1:]  # no reuse of flagship


def test_mapping_matches_descriptions():
    assert nv.resolve_model("wormv6.1") == "poolside/laguna-xs-2.1"      # coding
    assert nv.resolve_model("wormv6.2") == "nvidia/nemotron-3-ultra-550b-a55b"
    assert nv.resolve_model("wormv4.1") == "google/gemma-4-31b-it"       # high-speed logic
    assert nv.resolve_model("wormv4.0") == "nvidia/nemotron-3.5-bolt-e4b"  # lite/fast


def test_sanitize_drops_reasoning_content():
    data = {"model": "x", "choices": [
        {"message": {"content": "hi", "reasoning_content": "I am Nemotron"}}]}
    out = completions._sanitize(data)
    assert "reasoning_content" not in out["choices"][0]["message"]
    assert out["choices"][0]["message"]["content"] == "hi"


def test_mask_sse_removes_reasoning_in_delta():
    line = 'data: {"choices":[{"delta":{"content":"a","reasoning_content":"NVIDIA"}}]}'
    out = completions._mask_sse(line, "wormv6", "mistralai/mistral-large-4-1t-a52b")
    assert "reasoning_content" not in out and "NVIDIA" not in out


def test_ide_bundle_has_working_menu():
    """The IDE menubar must be the injected interactive component, not the
    upstream decorative label list that had no onClick handlers."""
    bundle = (Path(__file__).resolve().parent.parent
              / "site" / "assets" / "index-CeWFP5bj.js").read_text(encoding="utf-8")
    assert "Zq=(P)=>{const [open,setOpen]" in bundle          # menu component
    assert "a.jsx(Zq,{" in bundle                            # wired into the header
    assert '"File","Edit","Selection","View","Run","Terminal","Help"].map' not in bundle


def test_ide_bundle_has_folder_delete():
    """The explorer must offer a way to remove a folder and its files."""
    bundle = (Path(__file__).resolve().parent.parent
              / "site" / "assets" / "index-CeWFP5bj.js").read_text(encoding="utf-8")
    assert "[ZqDel,setZqDel]" in bundle                 # confirm-before-delete state
    assert 'title:ZqDel===L?"Click again to delete folder and its files"' in bundle
    assert 'item("Delete Folder","",P.onDeleteFolder,!P.hasActiveFolder)])' in bundle
    assert 'hasActiveFolder:$!=="Agent Project"' in bundle


def test_service_worker_revision_matches_bundle():
    """Precache must carry a content revision, else clients keep a stale bundle."""
    import hashlib
    site = Path(__file__).resolve().parent.parent / "site"
    digest = hashlib.md5((site / "assets" / "index-CeWFP5bj.js").read_bytes()).hexdigest()
    sw = (site / "sw.js").read_text(encoding="utf-8")
    assert f'index-CeWFP5bj.js",revision:"{digest}"' in sw


# --- multi-language runner -------------------------------------------------

import runner  # noqa: E402


def _run(payload):
    h = _auth_headers()
    return client.post("/api/run", headers=h, json=payload)


def test_runner_runs_python_and_reports_exit_code():
    r = _run({"files": [{"name": "main.py", "content": "print(6*7)"}]}).json()
    assert r["ok"] and r["language"] == "python"
    assert r["stdout"].strip() == "42" and r["exitCode"] == 0

    bad = _run({"files": [{"name": "main.py", "content": "raise SystemExit(3)"}]}).json()
    assert bad["ok"] is False and bad["exitCode"] == 3


def test_runner_compiles_cpp_and_c():
    cpp = _run({"files": [{"name": "m.cpp", "content":
                           '#include <iostream>\nint main(){std::cout<<"x";}'}]}).json()
    assert cpp["ok"] and cpp["language"] == "cpp" and cpp["stdout"] == "x"

    c = _run({"files": [{"name": "m.c", "content":
                         '#include <stdio.h>\nint main(){printf("y");}'}]}).json()
    assert c["ok"] and c["language"] == "c" and c["stdout"] == "y"


def test_runner_surfaces_compile_errors():
    r = _run({"files": [{"name": "bad.cpp", "content": "int main(){ this is not c++ }"}]}).json()
    assert r["ok"] is False and r["phase"] == "compile" and r["stderr"]


def test_runner_rejects_unknown_and_traversal():
    assert "Don't know how to run" in _run(
        {"files": [{"name": "notes.txt", "content": "hi"}], "entry": "notes.txt"}).json()["error"]
    assert "No runnable file" in _run(
        {"files": [{"name": "notes.txt", "content": "hi"}]}).json()["error"]
    assert _run({"files": [{"name": "../evil.py", "content": "print(1)"}]}).json()["ok"] is False
    assert client.post("/api/run", json={"files": [{"name": "a.py", "content": "1"}]}).status_code == 401


def test_runner_capabilities_lists_installed_toolchains():
    caps = client.get("/api/run/capabilities").json()["runtimes"]
    assert caps["python"] and caps["cpp"] and caps["javascript"]


def test_runner_times_out_instead_of_hanging():
    r = _run({"files": [{"name": "loop.py", "content": "while True: pass"}]}).json()
    assert r["ok"] is False and "timed out" in r["error"]


def test_ide_bundle_runs_code_and_previews_css():
    bundle = (Path(__file__).resolve().parent.parent
              / "site" / "assets" / "index-CeWFP5bj.js").read_text(encoding="utf-8")
    assert 'fetch("/api/run"' in bundle
    assert "ZqPreview=" in bundle
    assert '["html","css"].includes' in bundle


def test_ide_bundle_knows_extra_languages():
    bundle = (Path(__file__).resolve().parent.parent
              / "site" / "assets" / "index-CeWFP5bj.js").read_text(encoding="utf-8")
    for ext in ('cpp:"cpp"', 'rs:"rust"', 'go:"go"', 'rb:"ruby"', 'cxx:"cpp"', 'hpp:"cpp"'):
        assert ext in bundle
    assert 't==="cpp"?`#include <iostream>' in bundle


# --- community endpoints (sidebar panels) ----------------------------------

def test_community_endpoints_require_auth():
    store.SESSIONS.clear()
    for path in ("/api/my-files", "/api/partners", "/api/advertisement", "/api/mystery-box"):
        assert client.get(path).status_code == 401


def test_community_endpoints_return_json_not_spa_html():
    h = _auth_headers()
    for path, key in (("/api/my-files", "files"), ("/api/partners", "partners"),
                      ("/api/advertisement", "ads")):
        r = client.get(path, headers=h)
        assert r.status_code == 200 and r.json()[key] == []
        assert "text/html" not in r.headers.get("content-type", "")


def test_mystery_box_reports_no_ads_without_erroring():
    h = _auth_headers()
    body = client.get("/api/mystery-box", headers=h).json()
    assert body["canClaim"] is True and body["hasAd"] is False
    assert "message" in body


def test_advertisement_submit_round_trip():
    h = _auth_headers()
    r = client.post("/api/advertisement", headers=h,
                    json={"productName": "Acme", "productDetails": "d", "plan": "1 Week"})
    assert r.status_code == 200 and r.json()["ad"]["status"] == "pending"
    assert client.get("/api/advertisement", headers=h).json()["ads"][0]["productName"] == "Acme"
    assert client.post("/api/advertisement", headers=h, json={}).status_code == 400


def test_my_files_delete_and_missing_file_url():
    h = _auth_headers()
    assert client.get("/api/get-file-url?fileKey=nope", headers=h).status_code == 404
    assert client.request("DELETE", "/api/my-files", headers=h, json={"id": "x"}).json()["success"]

