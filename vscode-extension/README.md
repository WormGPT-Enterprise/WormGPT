# WormGPT for VS Code

Use WormGPT models inside the VS Code chat view.

## Install

1. Download `wormgpt-vscode.vsix` from the API Platform (`/integrations`) or
   from the "VSCode Integration" card on the site.
2. Install it in **VS Code** — do not double-click the file on Windows, that
   launches the Visual Studio installer (which then reports "one or more
   extensions are targeted at VS Code"). Either:
   - **Extensions → … → Install from VSIX…** and pick the file, or
   - from a terminal: `code --install-extension wormgpt-vscode.vsix`
3. Run the command **WormGPT: Set API Key** and paste a key created in the
   WormGPT API Platform (`wrm_live_...`).
4. Open the chat view, pick the **WormGPT** provider, and select a model.

## Settings

| Setting | Default | Description |
|---|---|---|
| `wormgpt.baseUrl` | `https://api.wormgpt.live/v1` | OpenAI-compatible gateway URL |
| `wormgpt.models` | `wormv6.2 … wormv4.0` | Model aliases shown in the picker |

The gateway must expose `POST /v1/chat/completions` (OpenAI-compatible) and
accept the key as a `Bearer` token. The backend in this repository already
does that.

## Build

```bash
npm install
npm run compile
python3 ../.tools/build_vsix.py     # writes dist/wormgpt-vscode.vsix
```
