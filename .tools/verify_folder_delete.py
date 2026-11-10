#!/usr/bin/env python3
"""End-to-end check for Worm IDE folder deletion (headless Chromium + CDP).

Creates a folder with a file in it, then verifies that the row trash icon
requires a confirming second click and that the confirming click removes both
the folder and the file it contained.
"""
import json, subprocess, sys, time, urllib.request
import websocket

PORT = 9414
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


ROWS = """[...document.querySelectorAll('button')].filter(b=>b.className.includes('w-full h-7'))"""
FILL = """(ph,val)=>{const i=[...document.querySelectorAll('input')].find(x=>x.placeholder===ph);
  if(!i)return false;const d=Object.getOwnPropertyDescriptor(i.constructor.prototype,'value').set;
  d.call(i,val);i.dispatchEvent(new Event('input',{bubbles:true}));
  i.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));return true}"""


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
            BASE + "/api/login", data=json.dumps({"username": "demotest", "password": "password123"}).encode(),
            headers={"Content-Type": "application/json"})).read())["token"]
        nav(BASE + "/signup")
        cdp.eval("localStorage.clear(); localStorage.setItem('sessionToken', %s);" % json.dumps(tok))
        nav(BASE + "/chat")
        cdp.eval("(()=>{const b=[...document.querySelectorAll('button')].find(x=>/^IDE \\[/.test(x.textContent.trim()));b&&b.click()})()")
        time.sleep(1.5)

        # folder "delme" + file "gone.js" inside it
        cdp.eval("(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.title==='New folder');b&&b.click()})()")
        time.sleep(0.4)
        print("folder input:", cdp.eval("(%s)('project-name','delme')" % FILL))
        time.sleep(0.8)
        cdp.eval("(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.title==='New file');b&&b.click()})()")
        time.sleep(0.4)
        print("file input:", cdp.eval("(%s)('src/app.ts','gone.js')" % FILL))
        time.sleep(0.8)

        rows = cdp.eval("(()=>%s.map(b=>b.textContent.trim()))()" % ROWS)
        print("rows before:", rows)
        assert any(r.startswith("delme") for r in rows), "folder not created"
        assert any("gone.js" in r for r in rows), "file not created"

        find_trash = ("(()=>{const r=%s.find(b=>b.textContent.trim().startsWith('delme'));"
                      "window.__t=r?[...r.querySelectorAll('span')].find(s=>s.className.includes('hover:text-red-300')):null;"
                      "return !!window.__t})()" % ROWS)
        print("folder has trash icon:", cdp.eval(find_trash))

        # first click arms, must not delete
        cdp.eval("(()=>{window.__t&&window.__t.click()})()")
        time.sleep(0.5)
        armed_title = cdp.eval("(()=>window.__t?window.__t.title:null)()")
        rows = cdp.eval("(()=>%s.map(b=>b.textContent.trim()))()" % ROWS)
        print("after 1st click -> title:", armed_title, "| still there:", any(r.startswith("delme") for r in rows))
        assert any(r.startswith("delme") for r in rows), "folder vanished on first click"

        # second click confirms: folder and its file must be gone
        cdp.eval("(()=>{window.__t&&window.__t.click()})()")
        time.sleep(0.8)
        rows = cdp.eval("(()=>%s.map(b=>b.textContent.trim()))()" % ROWS)
        print("rows after confirm:", rows)
        folders = cdp.eval("""(()=>{try{return JSON.parse(localStorage.getItem('worm-ide-workspace-v3')).folders}catch(e){return null}})()""")
        files = cdp.eval("""(()=>{try{return JSON.parse(localStorage.getItem('worm-ide-workspace-v3')).files.map(f=>f.name)}catch(e){return null}})()""")
        print("persisted folders:", folders, "| files:", files)

        # Scenario 2: File > Delete Folder acting on the selected folder.
        cdp.eval("(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.title==='New folder');b&&b.click()})()")
        time.sleep(0.4)
        cdp.eval("(%s)('project-name','filemenu')" % FILL)
        time.sleep(0.8)
        cdp.eval("(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.title==='New file');b&&b.click()})()")
        time.sleep(0.4)
        cdp.eval("(%s)('src/app.ts','menu-gone.js')" % FILL)
        time.sleep(0.8)
        # select the folder so it becomes the File > Delete Folder target
        cdp.eval("(()=>{const r=%s.find(b=>b.textContent.trim().startsWith('filemenu'));r&&r.click()})()" % ROWS)
        time.sleep(0.5)
        cdp.eval("(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='File');b&&b.click()})()")
        time.sleep(0.4)
        menu_del = cdp.eval("""(()=>{const b=[...document.querySelectorAll('button')]
          .find(x=>x.textContent.trim().startsWith('Delete Folder'));
          if(!b)return 'no-item'; if(b.disabled)return 'disabled'; b.click(); return 'clicked'})()""")
        time.sleep(0.8)
        rows2 = cdp.eval("(()=>%s.map(b=>b.textContent.trim()))()" % ROWS)
        folders2 = cdp.eval("""(()=>{try{return JSON.parse(localStorage.getItem('worm-ide-workspace-v3')).folders}catch(e){return null}})()""")
        print("File>Delete Folder:", menu_del, "| rows:", rows2, "| folders:", folders2)
        gone2 = (menu_del == "clicked"
                 and not any("filemenu" in r for r in rows2)
                 and not any("menu-gone.js" in r for r in rows2)
                 and "filemenu" not in (folders2 or []))
        # Guard: the built-in folder must not be deletable.
        cdp.eval("(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='File');b&&b.click()})()")
        time.sleep(0.4)
        guard = cdp.eval("""(()=>{const b=[...document.querySelectorAll('button')]
          .find(x=>x.textContent.trim().startsWith('Delete Folder'));
          if(!b)return 'no-item'; const d=b.disabled; b.click(); return d?'disabled':'ENABLED'})()""")
        time.sleep(0.5)
        cdp.eval("document.body.click()")
        rows3 = cdp.eval("(()=>%s.map(b=>b.textContent.trim()))()" % ROWS)
        print("guard (Agent Project):", guard, "| rows:", rows3)
        guard_ok = guard == "disabled" and any(r.startswith("Agent Project") for r in rows3)

        gone = guard_ok and gone2 and (not any(r.startswith("delme") for r in rows)
                and not any("gone.js" in r for r in rows)
                and "delme" not in (folders or [])
                and "gone.js" not in (files or []))
        print("RESULT:", "PASS" if gone else "FAIL")
        return 0 if gone else 1
    finally:
        proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
