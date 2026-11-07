#!/usr/bin/env python3
"""Use Chrome DevTools Protocol to extract the fully rendered /signup page."""
import base64, json, subprocess, sys, time, urllib.request
import websocket

PORT = 9411
CHROME = "chromium"
URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.wormgpt.co/signup"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/workspace/project/WormGPT/site"


def http(path, method="GET"):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), method=method)
    return json.load(urllib.request.urlopen(req))


def start():
    proc = subprocess.Popen([
        CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
        "--disable-dev-shm-usage", "--remote-debugging-port=%d" % PORT,
        "--remote-allow-origins=*", "--window-size=1440,2200", "--lang=en-US",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            http("/json/version")
            return proc
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("chromium did not start")


class CDP:
    def __init__(self, ws):
        self.ws = websocket.create_connection(ws, max_size=400 * 1024 * 1024)
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


def main():
    proc = start()
    try:
        t = http("/json/new?about:blank", "PUT")
        cdp = CDP(t["webSocketDebuggerUrl"])
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Page.navigate", {"url": URL})
        time.sleep(9)
        cdp.eval("""(()=>{const b=[...document.querySelectorAll('button')].find(x=>/Sign In to Existing Account/i.test(x.textContent));if(b)b.click()})()""")
        time.sleep(2)
        html = cdp.eval("document.documentElement.outerHTML")
        with open(OUT + "/signup.rendered.html", "w") as f:
            f.write("<!DOCTYPE html>\n" + html)
        styles = cdp.eval(r"""(()=>{
          const pick=(el)=>{if(!el)return null;const c=getComputedStyle(el);const r=el.getBoundingClientRect();
            return {tag:el.tagName,cls:(el.className||'').toString().slice(0,120),
              box:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
              color:c.color,bg:c.backgroundColor,font:c.fontFamily.split(',')[0],fs:c.fontSize,
              radius:c.borderRadius,border:c.borderColor,pad:c.padding};};
          const byText=(sel,txt)=>[...document.querySelectorAll(sel)].find(e=>new RegExp(txt,'i').test(e.textContent));
          return {
            html:{bg:getComputedStyle(document.documentElement).backgroundColor,color:getComputedStyle(document.documentElement).color},
            inputs:[...document.querySelectorAll('input')].map(pick),
            signinBtn:pick(byText('button','^\\s*Sign In\\s*$')),
            heading:pick(byText('h1,h2,h3,div','Welcome Back')),
          };})()""")
        with open(OUT + "/signup.styles.json", "w") as f:
            json.dump(styles, f, indent=2)
        m = cdp.send("Page.getLayoutMetrics")
        h = int(m["cssContentSize"]["height"])
        cdp.send("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": min(h, 9000),
                                                        "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1)
        shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
        with open(OUT + "/signup.png", "wb") as f:
            f.write(base64.b64decode(shot["data"]))
        print("URL:", cdp.eval("location.href"))
        print("DOM chars:", len(html))
        print("inputs:", json.dumps([i["box"] for i in (styles.get("inputs") or [])]))
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
