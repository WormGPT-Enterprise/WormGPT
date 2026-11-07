# 1. OBJECTIVE

Fix the two visible failures on the frontend's API Platform surface, and unlock
the premium features for the logged-in account:

1. `The server returned an invalid response (200)` on the API Platform page.
2. `Bad Gateway` when clicking **Create New Secret Key** on the **API Keys**
   page ("Manage authentication tokens used by your applications to communicate
   with the WormGPT Gateway.").
3. All premium-gated features render as available (no lock/PRO state) once the
   session license is loaded.

Out of scope (deferred): general cleanup/refactor of the API backend, real
persistence for chats/keys, and any non-premium feature work.

# 2. CONTEXT SUMMARY

Backend (FastAPI, clean rebuild):
- `app/main.py` — auth/session/license/models/chat-proxy/chats routes, then a
  catch-all `@app.get("/{path:path}")` (the SPA fallback) registered **last**.
  - `POST /api/login` / `/api/signup` -> `{success,user,license,token}` with
    `license = {"key":"CLEAN-REBUILD","type":"lifetime","credits":-1,"expires":None}`.
  - `GET /api/session`, `GET /api/license` -> `{success,user|license}`.
  - In-memory `SESSIONS` dict (token -> {user, license}).
- `app/chat_stream.py` — SSE relay to NVIDIA NIM.
- `app/nvidia_client.py` — alias map `wormv*` -> real NIM model ids.

Frontend (de-obfuscated SPA bundle `site/assets/index-CeWFP5bj.js`, single
minified line; served by the catch-all fallback):
- Confirmed UI strings present: `API Platform`, `API Keys`, `Your API Keys`,
  `No API keys`, `Create New Secret Key`, `Manage authentication tokens used by
  your applications to communicate with the WormGPT Gateway.`, `Endpoints`,
  `Playground`, `Documentation`, `Generate Key`, `Revoke`, `usage`,
  `rate limit`, `requests`, and the request header `X-API-Key`.
- Confirmed premium-gating tokens present: `licenseType`, `isPro`, `tier`,
  `features`, `unlimited`, `lifetime`, `subscription`, `expired`, `canUse`,
  `premium`, `license.type`, `type==="lifetime"`.
- Token stored in `localStorage` under `sessionToken`; requests use
  `Authorization: Bearer <token>`; error text uses `statusText` and the exact
  template `The server returned an invalid response (…)`.
- Bundle URL fragments present: `/api`, `/api/`, `/session`, `/login`,
  `/models`, `/license`, `/public-config`, `/chats`, `/chat-proxy`, `/usage`,
  `/keys`, `/create`, `/generate`, `/verify`. The exact API-keys paths are
  **built dynamically** (no literal `/api/keys`), so they must be extracted.

Root cause (hypothesis, to confirm in step 1):
- The catch-all `@app.get("/{path:path}")` is registered after all real routes,
  so any **GET `/api/<not-implemented>`** (API Platform list-keys/usage/
  endpoints) matches it and returns `site/index.html` (HTML) with HTTP **200**.
  The frontend calls `res.json()` on HTML and reports
  `The server returned an invalid response (200)`.
- **Create New Secret Key** issues a POST to an endpoint this backend does not
  implement, yielding a gateway/error status rendered as `Bad Gateway` (502).
- Premium stays locked because the UI checks fields the license payload does not
  provide (`licenseType`/`isPro`/`tier`/`premium`/`features`), while the backend
  only sends `{key,type,credits,expires}`.

Constraints / notes:
- The `grep` tool returns only file paths (the bundle is one line) and treats
  patterns as regex, so a small extraction script is needed to read surrounding
  context for any string.
- Preview ports: 12000 / 12001 (hosts listed in repo context).
- `.openhands/memory/*` describes an older Ollama/Venice layout and is stale for
  this tree; do not rely on it.

# 3. APPROACH OVERVIEW

Fix the fallback boundary first, then implement the API Platform endpoints and
the premium license shape, then verify end-to-end.

1. **Stop `/api/*` from falling through to the SPA.** Add an explicit JSON 404
   for unmatched `/api/*` paths and move/guard the SPA catch-all so it never
   serves HTML for API paths. This alone removes the misleading `(200)` and turns
   real gaps into honest JSON errors.
2. **Implement the API Platform endpoints** (keys list/create/revoke, usage,
   endpoints, docs/playground metadata) returning real demo data bound to the
   session, so the API Keys page renders and "Create New Secret Key" succeeds
   instead of `Bad Gateway`.
3. **Unlock premium** by returning the license fields the frontend gates on
   (`type:"lifetime"`, plus `isPro`/`tier`/`premium`/`features`/`unlimited` as
   the bundle expects) from `/api/login`, `/api/session`, `/api/license`.
4. **Verify** in the browser (ports 12000/12001) and with tests.

Rationale: the shared root cause is the fallback swallowing API paths; fixing
that first makes the remaining errors accurate, then the endpoint work is
straightforward. All data stays in-memory to match the existing demo design.

# 4. IMPLEMENTATION STEPS

## Step 1 — Extract the exact API Platform contract from the bundle
- **Goal:** Know the precise method + path + request/response shape for every API
  Platform call, and the exact premium gate fields.
- **Method:** Add a throwaway script `/.tools/extract_api.py` that reads
  `site/assets/index-CeWFP5bj.js`, and for each token (`API Keys`, `API Platform`,
  `Create New Secret Key`, `X-API-Key`, `usage`, `licenseType`, `isPro`, `tier`,
  `premium`, `features`, `unlimited`, `type==="lifetime"`) prints a window of
  ±200 chars so the surrounding fetch/URL logic is visible. Reconstruct each call
  site: HTTP method, path (often `\`${...}/keys\`` style), and JSON fields read
  from the response.
- **Reference:** `site/assets/index-CeWFP5bj.js`; helper `/.tools/extract_api.py`.
- **Deliverable:** A short table (method, path, request body, response fields) to
  drive step 3. No production code changed here.

## Step 2 — Stop API paths from hitting the SPA fallback
- **Goal:** Unmatched `/api/*` returns JSON 404, never `index.html`/HTML-200.
- **Method:** In `app/main.py`, register an explicit API catch-all **before** the
  SPA route, e.g. `@app.api_route("/api/{rest:path}", methods=[...])` returning
  `JSONResponse({"error":"Not found"}, 404)`. Keep the SPA `/{path:path}` route
  for non-`/api/` paths only (guard with an early `if path.startswith("api/"):`
  return 404 as a belt-and-braces fallback).
- **Reference:** `app/main.py` (catch-all at lines ~140–145; route ordering).
- **Deliverable:** `GET /api/does-not-exist` -> `404 application/json`.

## Step 3 — Implement the API Platform endpoints
- **Goal:** API Platform page and API Keys page load and work against this
  backend (demo data, session-scoped).
- **Method:** Add routes to `app/main.py` (or a new `app/api_platform.py`
  imported by `main.py`) using the paths/shapes from step 1. Minimum set:
  - `GET  <keys path>` -> `{"success":true,"keys":[...]}` (empty list ok; each
    item with the fields the UI reads, e.g. `id`/`name`/`prefix`/`createdAt`/
    `lastUsed`/`expires` — final names per step 1).
  - `POST <keys create path>` -> `{"success":true,"key":{"id":..., "secret":"sk-…"}}`
    (generate with `secrets.token_urlsafe`, store prefix + hash in memory only).
  - `POST/DELETE <keys revoke path>` -> `{"success":true}` and remove from store.
  - `GET  <usage path>` -> `{"success":true,"usage":{...}}` (zeros/demo).
  - `GET  <endpoints/docs path>` -> `{"success":true,"endpoints":[...]}` static
    metadata for the Endpoints/Documentation/Playground tabs.
  All routes require the `Bearer` session (reuse `_user_for`); return the same
  JSON error shape as existing routes.
- **Reference:** `app/main.py`, new `app/api_platform.py`, `SESSIONS` store.
- **Deliverable:** Clicking **Create New Secret Key** returns a JSON key (no
  `Bad Gateway`); the page lists keys and empty/usage state without errors.

## Step 4 — Unlock premium in the license payload
- **Goal:** No feature renders locked/PRO for the logged-in account.
- **Method:** Update the license object produced in `login`/`signup` and returned
  by `session`/`license` to include the gate fields confirmed in step 1 —
  e.g. keep `{key,type:"lifetime",credits:-1,expires:null}` and add
  `isPro:true`, `tier:"lifetime"`/`"pro"`, `premium:true`,
  `features:[...]`, `unlimited:true` (exact names/values from step 1). Centralize
  this in one `_license()` helper so every route returns the same shape.
- **Reference:** `app/main.py` (`login` license dict ~line 49; `_license` helper).
- **Deliverable:** Premium controls are enabled; no PRO/lock badges remain.

## Step 5 — Confirm no regressions in existing routes
- **Goal:** Auth/chat/chats still work after route reordering.
- **Method:** Re-run the existing suite (`python3 -m pytest -q`) and manually
  exercise login -> session -> chat-proxy SSE -> chats with `curl`.
- **Reference:** existing tests; `app/main.py`.

# 5. TESTING AND VALIDATION

Success criteria:
- `GET /api/<unimplemented>` returns `404` with `application/json` (not HTML-200).
- API Platform page loads with no `The server returned an invalid response`
  message; **Create New Secret Key** returns a JSON secret key and the list
  refreshes (no `Bad Gateway`).
- Endpoints/Documentation/Playground tabs render their metadata.
- After login, every premium-gated control is enabled and no PRO/lock state
  shows; `/api/session` and `/api/license` include the new gate fields.
- `python3 -m pytest -q` passes (existing behavior preserved).

How to verify:
- Start the app: `python3 app/run.py` (port 12000) and open the preview at
  `https://work-1-…:12000` / `https://work-2-…:12001`.
- Browser: log in, open API Platform and API Keys pages, click
  **Create New Secret Key**, and inspect the Network tab — API calls must return
  JSON (200) and no HTML.
- CLI: `curl -s -o /dev/null -w "%{http_code} %{content_type}\n" \
  http://localhost:12000/api/does-not-exist` -> `404 application/json`;
  `curl -s -H "Authorization: Bearer <token>" http://localhost:12000/api/session`
  -> license includes `isPro`/`tier`/`premium`/`features`.
- Automated: `python3 -m pytest -q` green.
