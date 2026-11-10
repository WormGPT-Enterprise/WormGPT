# WormGPT — pamięć projektu

## Czym jest
Lokalna aplikacja web (FastAPI + statyczny frontend) rozmawiająca z modelami Ollama.
UI odwzorowany 1:1 na https://wormgpt.ai/chat. Użytkownik mówi po polsku.

## Uruchomienie
```
pip install -r requirements.txt
OLLAMA_HOST=http://127.0.0.1:11434 python3 -m uvicorn app.main:app --host 0.0.0.0 --port 12000
```
Backend: `app/main.py` (`/api/models`, `/api/chat`, `/api/version`, `/api/health`,
`/api/venice/status`, `/api/venice/models`).
Frontend: `app/static/{index.html,style.css,app.js}` — bez zależności zewnętrznych,
ikony jako sprite SVG (lucide), brak CDN.

## Venice API (opcjonalny drugi provider) — od 2026-11-01
- `app/venice_client.py`: `list_models`, `check_access`, `stream_chat`,
  `resolve_model` (aliasy `worm-*` -> realne modele Venice; `ENGINE_ALIASES`).
- Klucz tylko przez `VENICE_API_KEY` w `.env` (patrz `.env.example`). Backend
  sprawdza klucz i saldo (`GET /api_keys/rate_limits`, NIE `/models` — ten
  zwraca 200 bez klucza, czyli fałszywy pozytyw).
- `POST /api/chat` przyjmuje `provider` = `ollama` (domyślnie) albo `venice`.
  Kontrakt `/api/models` pozostaje bez zmian.
- Frontend: silniki Venice są widoczne w menu Silnika, ale `disabled`, dopóki
  brak klucza LUB saldo = 0. Wtedy komunikat z linkiem do doładowania.
- Stan środowiska: zależności trzeba doinstalować (`pip install -r requirements.txt`),
  testy `python3 -m pytest -q` -> 37 przechodzi. Port podglądu UI: 12000 / 12001.
- PUŁAPKA NARZĘDZIOWA: `terminal`/`file_editor` z długimi argumentami (duży
  heredoc, długi `new_str`) gubią argumenty (puste `{}`) i zwracają błąd
  walidacji. Edytować małymi porcjami; szczegóły w daily logu.

## Backend API Platform (`/api/platform/*`) — od 2026-11-02
Klon wormgpt.co (FastAPI + NVIDIA NIM) ma panel `/platform` (klucze API,
usage, logi, billing). Frontend woła `/api/platform/keys` (GET/POST/PATCH/DELETE)
oraz `usage|logs|billing`. BRAK tych endpointów = "Create Secret Key" cicho
nie działa (SPA catch-all `/{path:path}` zwraca HTML na GET i 405 na POST).
Implementacja: `app/platform_api.py` (router) + wspólny stan `app/store.py`.
Reguła: surowy sekret (`sk-live-*`/`sk-test-*`) wraca TYLKO z POST; lista i
PATCH zwracają wyłącznie `keyHint`. Bramka `canUseApi` (`_d()` w bundlu)
przepuszcza `type==="lifetime"`/`admin` — więc brak klucza to bug backendu,
nie uprawnień. Testy: `app/test_platform_api.py`.

## NVIDIA NIM (backend czatu) — od 2026-11-02
Klucz w `app/.env` (`NVIDIA_API_KEY`; plik w .gitignore — NIE committować).
PUŁAPKA: `nvidia_client.py` MUSI wołać `load_dotenv(<app>/.env)` u siebie na
górze, bo `main.py` ładuje .env po imporcie klienta → inaczej `hasKey:false`.
PUŁAPKA: stara tabela `MODEL_ALIASES` wskazywała na wycofane modele (HTTP 410
Gone / 404). Konto ma dostęp tylko do podzbioru katalogu `/models` — wpis na
liście NIE znaczy, że model działa; sprawdzać realnym `POST /chat/completions`.
Działają: `nvidia/nemotron-3-ultra-550b-a55b` (flagowiec, tool_calls),
`poolside/laguna-xs-2.1` (kod, najszybszy), `nemotron-3-nano-omni-30b-a3b-reasoning`,
`nemotron-3.5-lightning-30b-a3b`, `nemotron-3.5-bolt-e4b`,
`minimaxai/minimax-m3.1-flash`, `meta/muse-glimmer-30b`. NIE działają:
wszystkie llama-3.x, qwen, deepseek-r1, mistral-nemotron, gemma, kimi, codestral.
UI wysyła też `wormv-auto` (domyślny) + legacy `wormv45.1`, `wormv-4` — mapowane.
REASONING: wyłącza się przez `chat_template_kwargs:{"thinking":false}` w body
(bezpieczne dla wszystkich modeli). `app/chat_stream.py` dodaje to, gdy brak
`isThinkingEnabled` (domyślnie OFF). Bundle frontendu wymuszał thinking dla
v6/v6.2 — spatchowany na `isThinkingEnabled:!!vt` (przełącznik użytkownika).

## Wygląd — zmierzone, nie zgadywane
Pełna geometria: `.openhands/reference/wormgpt-chat-geometry.md`.
Motyw = shadcn/ui ciemny: tło #0a0a0a, tekst #f2f2f2, wyciszony #8c8c8c,
obramowanie #292929, akcent #ec1313, promień 6px (karty 12px, pigułki 9999px).

Nieoczywiste fakty (łatwo pomylić się przy "odtwarzaniu z pamięci"):
- Pasek komunikatu nad nagłówkiem jest BURSZTYNOWY `rgba(245,158,11,0.9)`,
  `position: fixed`, i sam wygasa. Nie czerwony, nie zajmuje miejsca w układzie.
- Navbar `fixed` od y=0; treść ma `padding-top: 60px`.
- CTA ("Get Access") jest ZIELONY `#138643`.
- Aktywne linki nawigacji nie są wyróżnione kolorem.
- Karty hero: treść wyśrodkowana, 238x128, obramowanie 2px akcentu.
- Przyciski "+" i wyślij to kwadraty 48x48 (promień 6px), nie okręgi.
- Oryginał nie ma paska bocznego na desktopie.

Silnik (`#tool-engine`) — od 2026-11-01 DROPDOWN, nie atrapa:
- Klik otwiera `#engine-menu` w `.engine` (1:1 z komponentem `Nn` z oryginału):
  300px szer., max-h 70vh, padding 4px, radius 12px, odstęp 8px od pigułki.
- 5 grup z ikonami: 🔓 Uncensored (i-sparkles), 🛡️ Max Privacy (i-lock),
  🧠 Reasoning (i-cpu), ⚡ Fast & Cheap (i-zap), 👁️ Vision (i-eye); ikony 12x12.
- Katalog = 15 silników Venice z oryginału (`ENGINE_CATALOG`) + lokalne modele
  Ollamy z badge "Lokalny". Silniki Venice klikalne tylko gdy `veniceUsable()`
  (klucz + saldo > 0); inaczej `disabled` z badge "PRO".
- PUŁAPKA: kompozytor jest na dole, więc menu MUSI otwierać się do góry
  (`positionEngineMenu()` ustawia `data-side="top"`). Bez tego było obcięte.
- PUŁAPKA: menu Silnika i "+" wykluczają się nawzajem.


Persony — PRZYWRÓCONE (były usunięte, użytkownik kazał wrócić), od 2026-11-01 MODAL:
- `#tool-persona` to `<button class="tab tab-outline">` z ikoną i-drama
  ORAZ widoczną etykietą `#persona-label` (84x32, fs 12px). Gdy postać wybrana,
  etykieta = NAZWA postaci (np. "Batman", 116x32) + mały "×" (`#persona-pill-x`),
  klasa `is-on`, title "Postać: <nazwa>".
  NIE robić wersji ikonowej — użytkownik zgłosił to jako błąd ("zniknęła nazwa").
- Klik otwiera MODAL `#persona-modal` (1:1 z "Pick a Persona" z oryginału):
  max-w 42rem=672px, max-h 80vh, padding 24px, wyszukiwarka + "Wyczyść",
  siatka 2 kol., awatar 40px, ✓ przy wybranej, opis line-clamp-2.
- Dane: `app/static/personas.json` = 50 OBIEKTÓW {slug,name,description,tags,...}
  z edge function `venice-characters`. `tagline` i `avatarUrl` są tam ZAWSZE puste.
- `state.settings.persona` trzyma SLUG (nie nazwę!). `migratePersonaKey()`
  mapuje stare zapisy z nazwą. Do promptu idzie nazwa + opis (patrz daily log).

Menu pod przyciskiem "+" (`#plus-menu` w `.attach`) — jak w oryginale:
- 5 pozycji: Rozumowanie (przełącznik), Załącz plik, Generuj obraz,
  Generuj wideo, Wprowadzanie głosowe.
- Geometria: `bottom:calc(100% + 0.5rem)`, `left:0`, min-width 160px,
  padding 8px, gap 4px, radius 12px. Zmierzone 232x194, odstęp 8px od przycisku.
- Ikona plus obraca się o 45° przez klasę `.is-open` na `.attach`.
- Rozumowanie: `state.settings.reasoning` (DEFAULTS false), etykieta
  "Rozumowanie włączone", klasa `.is-on`, aria-checked; wstrzykuje do promptu
  instrukcję analizy krok po kroku.
- Głos: Web Speech API (pl-PL), wstawia tekst przez `dispatchEvent(new Event('input'))`.
- Załącz plik otwiera `#file-input`; obraz/wideo pokazują komunikat, że Ollama
  tego nie obsługuje (backend nie przyjmuje plików — `accept` to atrapa).
- KLUCZOWE: referencje DOM menu MUSZĄ być na górze app.js (linie ~30-42),
  bo `closePanels()` ich używa — inaczej ReferenceError (TDZ).

Narzędzia w oryginale (do ewentualnej rozbudowy):
- "Tools" to osobny przycisk z rozwijanym menu `w-80`: kategorie Reconnaissance,
  Scanning, Enumeration, Analysis, Deep Web Research z 11 narzędziami.
- U nas "Narzędzia" to na razie STATYCZNA pigułka `#tools-label` bez logiki.

Świadome odstępstwa od referencji (NIE "poprawiać" przy dalszym dopasowaniu):

## Metoda pomiaru oryginału (działa)
Chromium headless + CDP. Flaga `--remote-allow-origins=*` jest OBOWIĄZKOWA,
inaczej WebSocket odrzuca połączenie z błędem 403. Klient: `websocket-client` (pip).
Mierzyć `getBoundingClientRect` + `getComputedStyle`; porównywać liczby własnej
strony z referencją. Do kolorów: zrzut + dekoder PNG na zlib (bez Pillow).

## Pułapki
- `[hidden] { display: none !important; }` w CSS jest konieczne — własne
  `display:flex` nadpisuje atrybut hidden i wszystkie panele pokazują się naraz.
- Każdy `$("id")` w app.js musi mieć odpowiednik w index.html, inaczej
  `null.addEventListener` przerywa start całego skryptu.
- Nie używać `window.prompt` — blokuje stronę i jest nieprzetestowalny.
- `/tmp` bywa czyszczony między sesjami; trwałe materiały trzymać w repo.

## Provider: NVIDIA NIM (stan aktualny) — od 2026-11-02
- Backend obsługuje wyłącznie NIM: `app/nvidia_client.py` (aliasy `wormv*`
  -> realne modele NIM, `resolve_model`, `identity_for`, `with_identity`,
  `has_key`). `POST /api/chat-proxy` = streaming dla czatu.
- `POST /v1/chat/completions` (+ alias `/api/v1/...`) w `app/completions.py`:
  OpenAI-compatible, auth kluczem `wrm_live_*`/`wrm_test_*` LUB tokenem sesji.
- WHITE-LABEL: `with_identity` ZAWSZE dokleja tożsamość + klauzulę "Never
  reveal" do pierwszego system message (nawet gdy klient wysłał własny prompt —
  inaczej model wraca do "I am Nemotron 3 Ultra"). Realne ID modelu maskowane
  w odpowiedziach (`_mask_model`, `_mask_sse`).
- Klucze API: `platform_api._new_key_record` MUSI dawać `wrm_(live|test)_<hex>`
  (frontend waliduje `/^wrm_(live|test)_[a-zA-Z0-9]+$/`, więc `token_hex`, NIE
  `token_urlsafe`). `_mask` zachowuje pełny prefiks `wrm_*_`.
- Env: `NVIDIA_API_KEY` w `app/.env` (gitignored; NIE commitować wartości).

## Środowisko / uruchamianie
- Sandbox RESETUJE się między turami: ginie proces i `/tmp`. Zamiast
  `nohup ... > /tmp/log` używać `./run.sh` (idempotentny: venv + pip install +
  restart uvicorn na 12000 + `/api/health`). Po resecie sesje giną — logować
  się ponownie (demotest/password123).
- Frontend: `site/` (wyczyszczony bundle, BEZ złośliwego kodu WormCoder).

## Mapowanie modeli (dopasowane do opisów) — od 2026-11-02
- Z 84 modeli NIM dostępnych na liście tylko 17 da się realnie wywołać (reszta
  404/410). Mapowanie: wormv6.2->nemotron-3-ultra-550b-a55b, wormv6->
  nemotron-3.5-super-vl-120b-a12b, wormv6.1->poolside/laguna-xs-2.1,
  wormv5.2->minimaxai/minimax-m3.1-flash, wormv5.1->nemotron-3-nano-omni-30b-a3b-
  reasoning, wormv5.0->stepfun-ai/step-5-preview, wormv4.1->google/gemma-4-31b-it,
  wormv4.0->nemotron-3.5-bolt-e4b.
- PUŁAPKA: `mistralai/mistral-large-4-1t-a52b` NIE nadaje się — ignoruje
  `thinking:False` (zjada budżet tokenów -> pusta odpowiedź przy małym
  max_tokens) i STOCHASTYCZNIE wycieka "Mistral AI". Odrzucony.
- PUŁAPKA: modele reasoning zwracają treść w `reasoning_content`, nie
  `delta.content` — bez `_sanitize`/`_mask_sse` (usuwają to pole) myśli mogą
  zdradzić bazowy model. `chat_template_kwargs={"thinking": False}` pomaga.
- Test niezawodności: 6 trudnych promptów x 10 modeli = 0 wycieków przy
  realnym budżecie (700 tok.). Wcześniejsze "puste" to artefakt max_tokens=200.
- `/api/models`, `/api/health`, `/api/provider-status` są WHITE-LABEL
  (provider="WormGPT", bez `upstream`). Frontend ma własny katalog (bundle nie
  woła /api/models).

## Worm IDE — menu (FILES/EDIT/.../HELP) — od 2026-11-02
- Frontend to JEDEN zminifikowany plik `site/assets/index-CeWFP5bj.js` (Vite).
  Aliasy: `a` = react/jsx-runtime (`a.jsx`, `a.jsxs`, `a.Fragment`), `v` = React.
- Pasek menu w nagłówku IDE (`["File","Edit","Selection","View","Run",
  "Terminal","Help"]`) był DEKORACYJNY — przyciski bez `onClick`, więc martwe.
- Naprawa: `.tools/patch_ide_menu.py` (idempotentny) wstrzykuje komponent
  `Zq` (dropdowny + obsługa Escape/kliknięcia poza) i podmienia listę etykiet
  na `a.jsx(Zq,{...})`, podpinając WŁASNE handlery IDE: New File/Folder
  (`O("file"/"folder")`), Save (`localStorage worm-ide-workspace-v3`),
  Download (`re`), ZIP (`ke`), Run (`Me`), przełączniki (`x`/`S`/`A`/`_`),
  terminal (`z("terminal")`), log (`K`).
- PUŁAPKA: identyfikatory `NM` i `SM` SĄ już zajęte w bundle -> `SyntaxError:
  Identifier 'NM' has already been declared` (bundle to jeden scope). Przed
  wstrzyknięciem sprawdzić `\bNAZWA\b`; `Zq` jest wolne.
- PUŁAPKA: service worker (`site/sw.js`) precache'uje bundle z `revision:null`,
  więc klient trzyma STARY plik. Po zmianie bundle zaktualizować rewizję na
  md5 (`test_service_worker_revision_matches_bundle` tego pilnuje).
- Weryfikacja: `.tools/verify_ide_menu.py` (headless Chromium + CDP). Logowanie
  przez formularz przez CDP NIE działa (Turnstile/stan) — pobrać token z
  `POST /api/login` i wstrzyknąć `localStorage.setItem('sessionToken',...)`,
  potem wejść na `/chat`. Test klika 7 menu i tworzy plik (PASS).

## Usuwanie folderów w IDE (dodane, bo oryginał NIE MA tej funkcji)
- W oryginale wiersz folderu ma TYLKO "Download <folder>.zip"; brak kosza,
  brak `onContextMenu` (0 wystąpień). Nie da się usunąć folderu — jedyna droga
  to plik `worm-ide-workspace-v3` w localStorage (usunąć pliki, potem wpis
  z `folders`; kolejność ważna, bo lista = Set("Agent Project", folders, ...files.projectName)).
- Dodane przez `.tools/patch_ide_folder_delete.py` (po `patch_ide_menu.py`):
  1) kosz na wierszu folderu (hover, klasa `group` na wierszu), wymaga
     DRUGIEGO kliknięcia (stan `ZqDel` w ES, przycisk robi się czerwony),
  2) File → "Delete Folder" (disabled dla "Agent Project" przez `hasActiveFolder`).
- PUŁAPKA: `$` (zaznaczony folder) JEST doliczany do listy wierszy
  (`ws` = Set z `$`), więc po usunięciu zaznaczonego folderu trzeba zresetować
  zaznaczenie (`$===L&&q("Agent Project")`), inaczej wiersz zostaje na ekranie.
- Weryfikacja: `.tools/verify_folder_delete.py` (CDP) — 3 scenariusze: kosz
  z potwierdzeniem, File→Delete Folder, guard na Agent Project. PASS.

## Runner kodu w IDE (Run) — od sesji 5
- Oryginał: `Me` przy "Run" tylko dla HTML pokazywał preview, resztę kwitował
  komunikatem "other runtimes require a sandbox service". `PA` (języki) znał 20
  rozszerzeń, brak podświetlania składni w IDE (Prism NIE jest używany w IDE).
- Backend: `app/runner.py` + `POST /api/run` (+ `GET /api/run/capabilities`).
  Temp dir, argv bez shella, 20 s timeout, wyjście ≤60 kB, odrzuca `..`.
- Obsługiwane: python, javascript/mjs/cjs, jsx, ts, tsx, php, bash, ruby, go,
  rust, c, cpp (+cc/cxx/h/hpp). Rust MUSI iść jako kompilacja (rustc bez -O0,
  z `--edition 2021`) — wcześniej tylko się kompilował i nic nie wypisywał.
- Frontend: `.tools/patch_ide_languages.py` (rozszerzenia + startery) oraz
  `.tools/patch_ide_runner.py` (fetch /api/run + podgląd CSS w iframe).
  PUŁAPKA: marker idempotencji nie może być stringiem z tabel Prism
  (`scss:"scss"`, `cc:"cpp"` występują też w Prism!) — użyć `txt:"text"}[t||""]`.
- Zainstalowane runtime'y (apt): php-cli, ruby, golang-go, rustc,
  default-jdk-headless, lua5.4, mono-devel. **Warstwy apt NIE przeżywają
  restartu kontenera** — po restarcie `.tools/install_runtimes.sh`.
- PUŁAPKA: `shutil.which("./main.bin")` zwraca None (ścieżka relatywna!) —
  dla zbudowanych binarek użyć `_have_command` sprawdzającego plik w workdir.
- Swift: pakiet `swiftlang` to ~2 GB i wywalił restart środowiska; NIE
  instalować bez wyraźnej potrzeby.
- Panele boczne: `app/community_api.py` obsługuje /api/my-files, /api/get-file-url,
  /api/partners, /api/advertisement, /api/mystery-box (wcześniej SPA fallback
  zwracał HTML → panel czerwony).
- Weryfikacja: `.tools/verify_ide_languages.py` (CDP, 4 sprawdzenia) → PASS.

## API Platform — kontrakt z frontendem (od 2026-11-02)
- Frontend woła `${pt}/platform/*` gdzie `pt="/api"` (template literal, więc
  grep po `"/api/..."` tego NIE znajdzie — szukać `` `\${pt}/ ``).
- Parser odpowiedzi `yt()`: sukces => `{success:true, data:<JSON>}`; dane są
  pod `data`. Endpointy zwracają surowy JSON, nie kopertę `data`.
- Wiersz logu: `statusCode`, `timestamp`, `durationMs`, `promptTokens`,
  `completionTokens`, `totalTokens`, `keyName`. Bez nich tabela pokazuje
  `undefined` (wcześniej backend wysyłał `status`/`createdAt` — błąd).
- Streaming logowany w `finally` generatora SSE; gdy brak `usage`, tokeny
  szacowane z długości tekstu (playground nie ustawia `stream_options`).
- `dailyUsage` = jeden bucket na dzień, pola `date/formattedDate/requests/
  promptTokens/completionTokens/totalTokens/cost/errors`.
- `spendLimitUsd` => 429 po przekroczeniu.
- PUŁAPKA TESTOWA: `_auth_headers()` w test_platform_api.py musi czyścić
  `store.REQUEST_LOGS`, inaczej liczniki przeciekają między testami.

## Playground "Run Request" (od 2026-11-02)
- Handler to `Q` w komponencie `sU` (NIE `nU` — tamten to zakładka Overview).
- Klucz: `w`/`X()` (walidator `TS` = /^wrm_(live|test)_[a-zA-Z0-9]+$/),
  prompt: `u`, model: `l`, stream: `f` (domyślnie true).
- PUSTY prompt => w oryginale ciche `return` (objaw: "klikam i nic").
  Patch `.tools/patch_playground_feedback.py` dodaje komunikat.
- Po zmianie bundle'a ZAWSZE zaktualizować `revision` w `site/sw.js`
  (md5 pliku), inaczej service worker podaje stary plik.

## Testy
`pytest -q` → 31 testów (`app/test_platform_api.py`).

## Git
Remote: WormGPT-Enterprise/WormGPT. Gałąź `main`; lokalne commity NIE są
wypychane, chyba że użytkownik poprosi.

## Integracje (od 2026-11-02)
- „VSCode Integration" i „Full Source Code Access" z cennika mają realne
  endpointy w `app/integrations.py` (`/api/integrations/...`), stronę
  `/integrations` (`site/integrations.html`) i rozszerzenie VS Code
  (`vscode-extension/`, pakowane przez `.tools/build_vsix.py`, bez vsce).
- PUŁAPKA: `site/sw.js` ma `NavigationRoute` z denylistą. Każda nowa trasa
  nie-SPA (np. `/integrations`) MUSI tam trafić, inaczej cache'owany
  `index.html` ją zasłania. Po zmianie `index.html` zaktualizować jego
  `revision` w precache (md5). Testy: `app/test_integrations.py`.

## Uruchamianie VS Code (OpenVSCode Server) — od 2026-11-02
- W środowisku jest OpenVSCode Server (`$OPENVSCODE_SERVER_ROOT`, port 60001,
  token w `$OPENVSCODE_SERVER_ROOT/../`; port w `$OH_VSCODE_PORT`).
- Publiczny adres: `https://vscode-<RUNTIME_ID>.prod-runtime.all-hands.dev/?tkn=<token>&folder=workspace`.
  Dokładny URL (z tokenem) daje `GET http://127.0.0.1:60000/api/vscode/url`
  z nagłówkiem `X-Session-API-Key: $SESSION_API_KEY` (klucz jest w `/proc/1/environ`,
  NIE w env powłoki). `RUNTIME_URL` to Agent Server, nie edytor.
- Instalacja rozszerzenia: `.tools/install_vscode_extension.sh` (build + VSIX +
  `openvscode-server --install-extension`). Aktywację potwierdza
  `~/.openvscode-server/data/logs/*/exthost1/remoteexthost.log`.
