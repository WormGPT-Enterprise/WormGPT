#!/usr/bin/env bash
# Rebuild the WormGPT VS Code extension and install it into the local
# OpenVSCode Server so it shows up in the editor at OH_VSCODE_PORT.
set -eu
cd "$(dirname "$0")/.."

EXT_DIR="vscode-extension"
SERVER_ROOT="${OPENVSCODE_SERVER_ROOT:-/openhands/.openvscode-server}"
EXT_DIR_SERVER="${OPENVSCODE_EXTENSIONS_DIR:-$SERVER_ROOT/extensions}"

( cd "$EXT_DIR" && npm install --no-audit --no-fund && npm run compile )
python3 .tools/build_vsix.py

"$SERVER_ROOT/bin/openvscode-server" \
  --install-extension "$EXT_DIR/dist/wormgpt-vscode.vsix" \
  --extensions-dir "$EXT_DIR_SERVER"

echo "Installed. Open the editor at:"
python3 - <<'PY'
import json, os, urllib.request
key = os.environ.get("SESSION_API_KEY", "")
req = urllib.request.Request("http://127.0.0.1:60000/api/vscode/url",
                             headers={"X-Session-API-Key": key})
print(json.load(urllib.request.urlopen(req))["url"])
PY
