import io
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

import integrations  # noqa: E402
import main  # noqa: E402
import store  # noqa: E402

client = TestClient(main.app)
ROOT = Path(__file__).resolve().parent.parent


def _auth_headers():
    store.SESSIONS.clear()
    store.API_KEYS.clear()
    r = client.post("/api/login", json={"username": "tester", "password": "x"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _ensure_vsix():
    if not integrations.VSIX.exists():
        subprocess.run([sys.executable, str(ROOT / ".tools" / "build_vsix.py")],
                       check=True, capture_output=True)
    return integrations.VSIX


def test_vscode_config_is_openai_compatible():
    c = client.get("/api/integrations/vscode/config").json()
    assert c["vendor"] == "wormgpt"
    assert c["chatCompletionsUrl"].endswith("/v1/chat/completions")
    assert c["models"] and c["models"][0].startswith("wormv")
    assert c["vsixUrl"].endswith("/api/integrations/vscode/extension")


def test_vsix_is_a_valid_package():
    _ensure_vsix()
    r = client.get("/api/integrations/vscode/extension")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert z.testzip() is None
    names = z.namelist()
    assert "extension.vsixmanifest" in names
    assert "extension/package.json" in names
    pkg = z.read("extension/package.json").decode()
    assert '"languageModelChatProviders"' in pkg
    assert '"vendor": "wormgpt"' in pkg
    assert "extension/out/extension.js" in names


def test_source_manifest_excludes_secrets():
    h = _auth_headers()
    m = client.get("/api/integrations/source/manifest", headers=h).json()
    assert m["fileCount"] > 0
    paths = [f["path"] for f in m["files"]]
    assert "app/main.py" in paths
    assert not any(p.endswith(".orig") for p in paths)
    assert not any(p in ("app/.env", ".env") for p in paths)
    assert not any(".venv/" in p or "node_modules/" in p for p in paths)


def test_source_download_requires_auth_and_lifetime():
    store.SESSIONS.clear()
    assert client.get("/api/integrations/source/download").status_code == 401

    store.SESSIONS["tok-monthly"] = {
        "user": {"id": "u1", "username": "m"},
        "license": {"key": "K", "type": "monthly", "credits": 100, "expires": None},
    }
    r = client.get("/api/integrations/source/download",
                   headers={"Authorization": "Bearer tok-monthly"})
    assert r.status_code == 403


def test_source_download_zip_contains_code_only():
    h = _auth_headers()
    r = client.get("/api/integrations/source/download", headers=h)
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert z.testzip() is None
    names = z.namelist()
    assert any(n.endswith("app/main.py") for n in names)
    assert not any(n.endswith(".orig") for n in names)
    assert not any(n.endswith("app/.env") for n in names)
    assert not any("/node_modules/" in n for n in names)


def test_service_worker_lets_integrations_page_through():
    """The SW caches index.html for navigations; /integrations must be denied
    so the real page is served instead of the SPA shell."""
    sw = (ROOT / "site" / "sw.js").read_text(encoding="utf-8")
    assert "/^\\/integrations/" in sw
