# WormGPT — czysty rebuild (frontend + backend)

Klony 1:1 frontendu WORMGPT (`/signup`) **z usuniętym złośliwym kodem**,
plus własny, czysty backend czatu oparty o **NVIDIA NIM**.

## Co zostało USUNIĘTE z frontendu
Ze bundla `site/assets/index-CeWFP5bj.js` wycięto (bundle nadal parsuje się
poprawnie, `node --check`):
- generator "WormCoder" — keylogger, strony phishingowe, `harvester.php`
- "Sample Cyber Kits" (presety ataków)
- cały "Ultra Laboratory Suite" (Web Scanner, SQL Auditor, Payload Store)
- komponent Email OSINT i endpoint `/api/email-osint`

Backup oryginału: `site/assets/index-CeWFP5bj.js.orig` (gitignored).

## Backend (własny, czysty) — `app/`
Implementuje dokładnie ten kontrakt API, którego oczekuje frontend:

| Endpoint | Opis |
|---|---|
| `GET  /api/public-config` | testowy sitekey -> frontend pomija Turnstile |
| `POST /api/login`, `/api/signup` | sesja demo, zwraca token |
| `GET  /api/session`, `/api/license` | stan sesji |
| `POST /api/logout` | wylogowanie |
| `GET  /api/models` | lista aliasów modeli |
| `POST /api/chat-proxy` | streaming SSE z NVIDIA NIM |
| `POST /v1/chat/completions` | **OpenAI-compatible** (alias `/api/v1/...`), klucz `wrm_live_*`/`wrm_test_*` |
| `GET/POST /api/platform/keys` | klucze API platformy (format `wrm_(live|test)_<hex>`) |
| `POST /api/run` | **wykonuje kod** z IDE (13 języków: Python, JS/TS, PHP, Bash, Ruby, Go, Rust, Lua, Java, C#, C, C++) |
| `GET  /api/run/capabilities` | które runtime'y są zainstalowane na serwerze |
| `GET  /api/my-files`, `/api/partners`, `/api/advertisement`, `/api/mystery-box` | panele boczne (bez błędów czerwonych) |
| `GET  /api/chats`, `POST /api/chats-wipe` | historia (demo, in-memory) |

Provider: **NVIDIA NIM** (OpenAI-compatible), `app/nvidia_client.py` mapuje
aliasy `wormv*` na realne modele, np. `wormv6` -> `meta/llama-3.3-70b-instruct`.

**White-labeling**: backend wstrzykuje tożsamość WormGPT per alias i klauzulę
zakazującą ujawniania modelu bazowego/dostawcy; realne ID modelu jest maskowane
w odpowiedziach (także w strumieniu SSE).

## Uruchomienie
```bash
pip install -r requirements.txt
export NVIDIA_API_KEY=nvapi-...        # albo wpisz do app/.env
python3 app/run.py                     # http://localhost:12000
```
Bez klucza backend działa, ale czat zwraca komunikat "NVIDIA_API_KEY is not set".

## Uruchamianie kodu w IDE
Przycisk **Run** wysyła pliki projektu do `POST /api/run`; serwer zapisuje je
w katalogu tymczasowym i uruchamia interpreter/kompilator obecny na hoście
(`python3`, `node`, `php`, `bash`, `gcc`, `g++`, `ruby`, `go`, `rustc`,
`lua5.4`, `javac`/`java`, `mcs`/`mono`).
Wyjście (stdout/stderr + kod wyjścia) wraca do panelu Terminal. CSS jest
renderowane w zakładce Preview (arkusz wstrzykiwany do przykładowej strony).
Zainstalowane na tym hoście: Python 3.13, Node 24 (z natywnym TS), GCC/G++ 14,
PHP 8.4, Ruby 3.3, Go 1.24, Rust 1.85, Lua 5.4, OpenJDK 21, Mono C# 6.12.
Limit: 20 s, wyjście ucinane do 60 kB. Warstwy `apt` nie przeżywają restartu
kontenera — po restarcie uruchom `.tools/install_runtimes.sh`.

## Struktura
```
site/     frontend (wyczyszczony bundle + shell)
app/      backend: main.py, chat_stream.py, nvidia_client.py, run.py
.tools/   serve.py (statyk+proxy), capture.py, strip.py (usuwanie złego kodu)
reference/ dowody 1:1 (zrzuty, zmierzone style)
```
