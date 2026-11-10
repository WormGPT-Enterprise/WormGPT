#!/usr/bin/env python3
"""Drive headless Chromium over CDP to verify the Worm IDE menubar works.

Logs in, opens the IDE, clicks each menu, and asserts the dropdown entries
appear and that a representative action mutates the workspace.
"""
import json, subprocess, sys, time, urllib.request
import websocket

PORT = 9412
CHROME = "chromium"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:12000"


def http(path, method="GET"):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), method=method)
    return json.load(urllib.request.urlopen(req))


def start():
    proc = subprocess.Popen([
        CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
        "--disable-dev-shm-usage", "--remote-debugging-port=%d" % PORT,
        "--remote-allow-origins=*", "--window-size=1600,1000", "--lang=en-US",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            http("/json/version")
            return proc
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
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def eval(self, expr):
        r = self.send("Runtime.evaluate", {
            "expression": expr, "returnByValue": True, "awaitPromise": True})
        res = r.get("result", {})
        if res.get("subtype") == "error":
            raise RuntimeError(res.get("description"))
        return res.get("value")


def main():
    proc = start()
    try:
        tabs = http("/json/list")
        page = [t for t in tabs if t["type"] == "page"][0]
        cdp = CDP(page["webSocketDebuggerUrl"])
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")

        def nav(url):
            cdp.send("Page.navigate", {"url": url})
            for _ in range(80):
                time.sleep(0.25)
                if cdp.eval("document.readyState") == "complete":
                    break
            time.sleep(1.5)

        # Obtain a real session token, then seed it the way the SPA stores it.
        tok = json.loads(urllib.request.urlopen(urllib.request.Request(
            BASE + "/api/login", data=json.dumps(
                {"username": "demotest", "password": "password123"}).encode(),
            headers={"Content-Type": "application/json"})).read())["token"]
        nav(BASE + "/signup")
        cdp.eval("localStorage.setItem('sessionToken', %s);" % json.dumps(tok))
        nav(BASE + "/chat")
        time.sleep(2)

        # Open the IDE
        opened = cdp.eval("""(()=>{
          const b=[...document.querySelectorAll('button')].find(x=>/^IDE \\[/.test(x.textContent.trim()));
          if(b){b.click();return true} return false;
        })()""")
        time.sleep(1.5)
        print("IDE opened:", opened)

        def menu_buttons():
            return cdp.eval("""(()=>[...document.querySelectorAll('button')]
              .filter(x=>['File','Edit','Selection','View','Run','Terminal','Help'].includes(x.textContent.trim()))
              .map(x=>x.textContent.trim()))()""")
        print("menu buttons:", menu_buttons())

        results = {}
        for name, expect in [("File", "New File"), ("Edit", "Undo"),
                             ("Selection", "Select All"), ("View", "Explorer"),
                             ("Run", "Run File"), ("Terminal", "Show Terminal"),
                             ("Help", "Keyboard Shortcuts")]:
            cdp.eval("""(()=>{
              const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()===%s);
              if(b)b.click(); return !!b;
            })()""" % json.dumps(name))
            time.sleep(0.4)
            items = cdp.eval("""(()=>[...document.querySelectorAll('button')]
              .map(x=>x.textContent.trim())
              .filter(t=>t && !['File','Edit','Selection','View','Run','Terminal','Help'].includes(t)))()""")
            hit = any(expect.lower() in (t or "").lower() for t in items)
            results[name] = (hit, items)
            # close
            cdp.eval("""document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))""")
            cdp.eval("""window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))""")
            time.sleep(0.3)

        ok = True
        for name, (hit, items) in results.items():
            print(f"{name}: {'OK' if hit else 'MISSING'} -> {items}")
            ok = ok and hit

        # Exercise a real action: File -> New File should open the explorer input
        cdp.eval("""(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='File');b&&b.click()})()""")
        time.sleep(0.4)
        cdp.eval("""(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim().startsWith('New File'));b&&b.click()})()""")
        time.sleep(0.6)
        has_input = cdp.eval("""(()=>{
          return !!document.querySelector('input[placeholder="src/app.ts"]')
            || [...document.querySelectorAll('input')].some(i=>i.placeholder==='src/app.ts');
        })()""")
        print("New File opened the name input:", has_input)

        # Complete the flow: type a name, press Enter, expect the file to open.
        created = cdp.eval("""(()=>{
          const inp=[...document.querySelectorAll('input')].find(i=>i.placeholder==='src/app.ts');
          if(!inp) return false;
          const d=Object.getOwnPropertyDescriptor(inp.constructor.prototype,'value').set;
          d.call(inp,'hello.js'); inp.dispatchEvent(new Event('input',{bubbles:true}));
          inp.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
          return true;
        })()""")
        time.sleep(1.0)
        tabs = cdp.eval("""(()=>[...document.querySelectorAll('button')]
          .map(x=>x.textContent.trim()).filter(t=>t && t.indexOf('hello.js')!==-1))()""")
        print("New File created a tab:", created, tabs)

        good = ok and has_input and opened and created and bool(tabs)
        print("RESULT:", "PASS" if good else "FAIL")
        return 0 if good else 1
    finally:
        proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
