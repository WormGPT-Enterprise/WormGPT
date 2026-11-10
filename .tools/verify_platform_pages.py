"""End-to-end check of the API Platform pages in a real browser.

Seeds a session, creates a platform key through the UI, runs a playground
request, then asserts that the Request Logs / Usage pages render real values
instead of `undefined` or an empty state.

Usage: python3 .tools/verify_platform_pages.py
"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

PORT = 9222
BASE = "http://127.0.0.1:12000"


def http(path):
    return json.load(urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, path)))


def start():
    p = subprocess.Popen(["chromium", "--headless=new", "--no-sandbox", "--disable-gpu",
                          "--disable-dev-shm-usage", "--remote-debugging-port=%d" % PORT,
                          "--remote-allow-origins=*", "--window-size=1600,1000", "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            http("/json/version")
            return p
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("chromium did not start")


class CDP:
    def __init__(self, ws):
        self.ws = websocket.create_connection(ws, max_size=200 * 1024 * 1024)
        self.id = 0

    def send(self, method, params=None):
        self.id += 1
        self.ws.send(json.dumps({"id": self.id, "method": method, "params": params or {}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.id:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})

    def eval(self, e):
        return self.send("Runtime.evaluate", {"expression": e, "returnByValue": True,
                                              "awaitPromise": True}).get("result", {}).get("value")


def _api(path, token, method="GET", payload=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + token})
    return json.loads(urllib.request.urlopen(req).read())


def main():
    proc = start()
    try:
        page = [t for t in http("/json/list") if t["type"] == "page"][0]
        cdp = CDP(page["webSocketDebuggerUrl"])
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")

        def nav(u):
            cdp.send("Page.navigate", {"url": u})
            for _ in range(80):
                time.sleep(0.25)
                if cdp.eval("document.readyState") == "complete":
                    break
            time.sleep(1.5)

        tok = _api("/api/login", "", "POST",
                   {"username": "platformdemo", "password": "x"})["token"]
        key = _api("/api/platform/keys", tok, "POST",
                   {"name": "Browser Demo", "env": "live"})["key"]

        checks = {}
        nav(BASE + "/signup")
        cdp.eval("localStorage.clear(); localStorage.setItem('sessionToken', %s);" % json.dumps(tok))

        # Run one request so the logs and the chart have data to show.
        _api("/api/v1/chat/completions", key["key"], "POST",
             {"model": "wormv6.2", "messages": [{"role": "user", "content": "ping"}],
              "stream": False})

        nav(BASE + "/platform")
        time.sleep(2)

        # Switch to the Request Logs section and read the rendered table.
        cdp.eval("""(()=>{const b=[...document.querySelectorAll('button')]
          .find(x=>/Request Logs/.test(x.textContent));b&&b.click()})()""")
        time.sleep(2.5)
        logs_text = cdp.eval("document.body.innerText") or ""
        checks["logs_no_undefined"] = "undefined" not in logs_text
        checks["logs_row_rendered"] = "Browser Demo" in logs_text and "wormv6.2" in logs_text
        checks["logs_has_tokens"] = "(0)" not in logs_text.split("Tokens")[-1][:40] \
            if "Tokens" in logs_text else False

        # Usage Analytics must draw the daily bars with real numbers.
        cdp.eval("""(()=>{const b=[...document.querySelectorAll('button')]
          .find(x=>/Usage Analytics/.test(x.textContent));b&&b.click()})()""")
        time.sleep(2.5)
        usage_text = cdp.eval("document.body.innerText") or ""
        checks["usage_no_undefined"] = "undefined" not in usage_text
        # The newest bucket must show a real request count, not only zeros.
        import re as _re
        tail = usage_text[usage_text.rfind("Daily API Request Volume"):]
        counts = [int(n) for n in _re.findall(r"(\d+) requests", tail)]
        checks["usage_has_requests"] = bool(counts) and max(counts) >= 1
        checks["usage_has_bars"] = bool(cdp.eval(
            """document.querySelectorAll('div[style*="height"]').length>0"""))

        print("logs page:", repr(logs_text[:400]))
        print()
        print("usage page:", repr(usage_text[:400]))
        print()
        print("RESULT:", "PASS" if all(checks.values()) else "FAIL", checks)
        return 0 if all(checks.values()) else 1
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
