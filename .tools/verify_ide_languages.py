#!/usr/bin/env python3
"""End-to-end check for the Worm IDE multi-language support (CDP).

Verifies in a real browser that:
* a new .cpp file is recognised as C++ and seeded with a starter template;
* Run sends the workspace to /api/run and prints the program's output;
* a compile error is reported instead of silently doing nothing;
* a .css file previews inside the panel iframe.
"""
import json, subprocess, sys, time, urllib.request
import websocket

PORT = 9415
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:12000"


def http(path):
    return json.load(urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, path)))


def start():
    p = subprocess.Popen(["chromium", "--headless=new", "--no-sandbox", "--disable-gpu",
                          "--disable-dev-shm-usage", "--remote-debugging-port=%d" % PORT,
                          "--remote-allow-origins=*", "--window-size=1600,1000", "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            http("/json/version"); return p
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("chromium did not start")


class CDP:
    def __init__(self, ws):
        self.ws = websocket.create_connection(ws, max_size=200 * 1024 * 1024); self.id = 0

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


NEW_FILE_OPEN = """(()=>{const b=[...document.querySelectorAll('button')]
  .find(x=>x.title==='New file');if(!b)return 'no-button';b.click();return 'ok'})()"""

NEW_FILE_FILL = """(name)=>{
  const i=[...document.querySelectorAll('input')].find(x=>x.placeholder==='src/app.ts');
  if(!i) return 'no-input';
  const d=Object.getOwnPropertyDescriptor(i.constructor.prototype,'value').set;
  d.call(i,name); i.dispatchEvent(new Event('input',{bubbles:true}));
  i.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  return 'ok';
}"""


def create_file(cdp, name):
    cdp.eval(NEW_FILE_OPEN); time.sleep(0.5)
    return cdp.eval("(%s)(%r)" % (NEW_FILE_FILL, name))

RUN_CLICK = """(()=>{const b=[...document.querySelectorAll('button')]
  .find(x=>x.textContent.trim()==='Run'&&x.className.includes('px-2.5'));
  if(!b)return 'no-run';b.click();return 'ok'})()"""

TERMINAL_TEXT = """(()=>{const p=[...document.querySelectorAll('pre')]
  .find(x=>x.className.includes('whitespace-pre-wrap'));return p?p.textContent:''})()"""


def main():
    proc = start()
    try:
        page = [t for t in http("/json/list") if t["type"] == "page"][0]
        cdp = CDP(page["webSocketDebuggerUrl"])
        cdp.send("Page.enable"); cdp.send("Runtime.enable")

        def nav(u):
            cdp.send("Page.navigate", {"url": u})
            for _ in range(80):
                time.sleep(0.25)
                if cdp.eval("document.readyState") == "complete":
                    break
            time.sleep(1.5)

        tok = json.loads(urllib.request.urlopen(urllib.request.Request(
            BASE + "/api/login", data=json.dumps({"username": "demotest", "password": "x"}).encode(),
            headers={"Content-Type": "application/json"})).read())["token"]
        nav(BASE + "/signup")
        cdp.eval("localStorage.clear(); localStorage.setItem('sessionToken', %s);" % json.dumps(tok))
        nav(BASE + "/chat")
        cdp.eval("(()=>{const b=[...document.querySelectorAll('button')].find(x=>/^IDE \\[/.test(x.textContent.trim()));b&&b.click()})()")
        time.sleep(1.5)

        checks = {}

        # 1. .cpp is recognised and seeded
        print("new cpp:", create_file(cdp, "prog.cpp"))
        time.sleep(1.0)
        checks["cpp_recognised"] = cdp.eval(
            """(()=>{const t=document.querySelector('textarea[wrap="off"]');return !!t&&t.value.includes('#include <iostream>')})()""")
        print("cpp seeded with template:", checks["cpp_recognised"])

        # 2. Run it -> backend output in the terminal panel
        cdp.eval(RUN_CLICK)
        time.sleep(4)
        text = cdp.eval(TERMINAL_TEXT) or ""
        print("terminal:", repr(text[-300:]))
        checks["cpp_ran"] = "Hello from Worm IDE" in text and "OK cpp" in text

        # 3. a compile error is surfaced
        cdp.eval("""(()=>{const t=document.querySelector('textarea[wrap="off"]');
          const d=Object.getOwnPropertyDescriptor(t.constructor.prototype,'value').set;
          d.call(t,'int main(){ this is not c++ }');
          t.dispatchEvent(new Event('input',{bubbles:true}))})()""")
        time.sleep(0.5)
        cdp.eval(RUN_CLICK)
        time.sleep(4)
        text2 = cdp.eval(TERMINAL_TEXT) or ""
        print("terminal after bad code:", repr(text2[-300:]))
        checks["compile_error"] = ("error" in text2.lower() or "FAIL" in text2) and "OK cpp" not in text2.split("$ Running")[-1]

        # 4. CSS preview
        print("new css:", create_file(cdp, "style.css"))
        time.sleep(1.0)
        cdp.eval("""(()=>{const t=document.querySelector('textarea[wrap="off"]');
          const d=Object.getOwnPropertyDescriptor(t.constructor.prototype,'value').set;
          d.call(t,'body { background: rgb(1, 2, 3); }');
          t.dispatchEvent(new Event('input',{bubbles:true}))})()""")
        time.sleep(0.4)
        cdp.eval(RUN_CLICK)
        time.sleep(2.5)
        checks["css_preview"] = cdp.eval("""(()=>{const f=document.querySelector('iframe[title="Project preview"]');
          return !!f && f.getAttribute('srcdoc').includes('background: rgb(1, 2, 3)')})()""")
        print("css preview iframe:", checks["css_preview"])

        print("RESULT:", "PASS" if all(checks.values()) else "FAIL", checks)
        return 0 if all(checks.values()) else 1
    finally:
        proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
