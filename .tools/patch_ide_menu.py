#!/usr/bin/env python3
"""Inject a working Worm IDE menubar into the shipped frontend bundle.

The upstream Vite bundle renders the IDE menu labels (File/Edit/Selection/
View/Run/Terminal/Help) as buttons without any onClick, so every entry is
dead. This script defines a `NM` menu component in the bundle's top scope and
swaps the decorative label list for it, wiring each entry to the IDE's own
handlers (new file/folder, save, download, ZIP export, run, panel toggles,
terminal, help). Idempotent: running it twice is a no-op.
"""
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent / "site" / "assets" / "index-CeWFP5bj.js"

Zq = (
    'Zq=(P)=>{'
    'const [open,setOpen]=v.useState(null);'
    'const ref=v.useRef(null);'
    'v.useEffect(()=>{'
    'const h=e=>{ref.current&&!ref.current.contains(e.target)&&setOpen(null)};'
    'const k=e=>{e.key==="Escape"&&setOpen(null)};'
    'window.addEventListener("mousedown",h);window.addEventListener("keydown",k);'
    'return ()=>{window.removeEventListener("mousedown",h);window.removeEventListener("keydown",k)};'
    '},[]);'
    'const run=fn=>{setOpen(null);try{fn&&fn()}catch(e){}};'
    'const item=(label,acc,fn,dis)=>a.jsxs("button",{type:"button",disabled:!!dis,'
    'onClick:()=>run(fn),'
    'className:"w-full flex items-center justify-between gap-6 px-2.5 py-1.5 rounded text-left text-[11px] text-zinc-300 hover:bg-white/[0.06] disabled:opacity-30",'
    'children:[a.jsx("span",{children:label}),acc?a.jsx("span",{className:"text-[9px] text-zinc-600",children:acc}):null]},label);'
    'const exec=c=>()=>{try{document.execCommand(c)}catch(e){}};'
    'const menu=(name,items)=>a.jsxs("div",{className:"relative",children:['
    'a.jsx("button",{type:"button",onClick:()=>setOpen(o=>o===name?null:name),'
    'className:open===name?"px-1.5 py-1 rounded text-[11px] text-zinc-100 bg-white/[0.08]":"px-1.5 py-1 rounded text-[11px] text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.06]",'
    'children:name}),'
    'open===name?a.jsx("div",{className:"absolute left-0 top-[calc(100%+4px)] z-[90] w-56 rounded-lg border border-white/[0.08] bg-[#1b1b1b] p-1 shadow-[0_18px_40px_rgba(0,0,0,0.55)]",children:items}):null'
    ']},name);'
    'return a.jsxs("div",{ref:ref,className:"hidden xl:flex items-center gap-0.5 ml-2",children:['
    'menu("File",['
    'item("New File","Ctrl+N",P.onNewFile),'
    'item("New Folder","",P.onNewFolder),'
    'item("Save File","Ctrl+S",P.onSave,!P.hasActiveFile),'
    'item("Download File","",P.onDownloadFile,!P.hasActiveFile),'
    'item("Download Project ZIP","",P.onExportZip),'
    'item("Close Editor","",P.onClose,!P.onClose)]),'
    'menu("Edit",['
    'item("Undo","Ctrl+Z",exec("undo")),'
    'item("Redo","Ctrl+Y",exec("redo")),'
    'item("Cut","Ctrl+X",exec("cut")),'
    'item("Copy","Ctrl+C",exec("copy")),'
    'item("Paste","Ctrl+V",exec("paste"))]),'
    'menu("Selection",['
    'item("Select All","Ctrl+A",()=>{const el=P.editorRef&&P.editorRef.current;if(el){el.focus();el.select()}else{try{document.execCommand("selectAll")}catch(e){}}})]),'
    'menu("View",['
    'item((P.showExplorer?"Hide":"Show")+" Explorer","",P.onToggleExplorer),'
    'item((P.showAgent?"Hide":"Show")+" Agent Panel","",P.onToggleAgent),'
    'item((P.showPanel?"Hide":"Show")+" Panel","",P.onTogglePanel),'
    'item(P.isFullscreen?"Exit Fullscreen":"Enter Fullscreen","",P.onToggleFullscreen)]),'
    'menu("Run",['
    'item("Run File","",P.onRun),'
    'item("Preview in Browser","",P.onPreview)]),'
    'menu("Terminal",['
    'item("Show Terminal","",P.onShowTerminal),'
    'item("Toggle Panel","",P.onTogglePanel),'
    'item("Clear Logs","",P.onClearLogs)]),'
    'menu("Help",['
    'item("Keyboard Shortcuts","",P.onShortcuts),'
    'item("About Worm IDE","",P.onAbout)])'
    ']});'
    '},'
)

OLD_ANCHOR = ",ES=({workspaceFiles:"
NEW_ANCHOR = "," + Zq + "ES=({workspaceFiles:"

OLD_MENUBAR = (
    'children:["File","Edit","Selection","View","Run","Terminal","Help"]'
    '.map(L=>a.jsx("button",{className:"px-1.5 py-1 rounded text-[11px] text-zinc-500 '
    'hover:text-zinc-200 hover:bg-white/[0.06]",children:L},L))'
)

NEW_MENUBAR = (
    'children:a.jsx(Zq,{'
    'onNewFile:()=>O("file"),onNewFolder:()=>O("folder"),'
    'hasActiveFile:!!Xe,'
    'onSave:()=>{try{localStorage.setItem("worm-ide-workspace-v3",JSON.stringify({'
    'files:ra.current,tabs:s,activeId:n,chats:pn,activeChatId:zn,folders:Y}));'
    'K(le=>[...le,"Workspace saved."])}catch(e){}},'
    'onDownloadFile:re,onExportZip:()=>ke(),onClose:o,editorRef:ln,'
    'showExplorer:f,onToggleExplorer:()=>x(L=>!L),'
    'showAgent:w,onToggleAgent:()=>S(L=>!L),'
    'showPanel:T,onTogglePanel:()=>A(L=>!L),'
    'isFullscreen:D,onToggleFullscreen:()=>_(L=>!L),'
    'onRun:Me,onPreview:()=>{A(!0),z("preview")},'
    'onShowTerminal:()=>{A(!0),z("terminal")},onClearLogs:()=>K([]),'
    'onShortcuts:()=>K(L=>[...L,"Shortcuts: Ctrl+S save, Ctrl+P search, Ctrl+N new file."]),'
    'onAbout:()=>K(L=>[...L,"Worm IDE - agentic code workspace by WormGPT."])})'
)


def main():
    src = BUNDLE.read_text(encoding="utf-8")
    if "Zq=(P)=>{const [open,setOpen]" in src:
        print("already patched")
        return 0
    for anchor in (OLD_ANCHOR, OLD_MENUBAR):
        if anchor not in src:
            print(f"anchor not found: {anchor[:60]!r}", file=sys.stderr)
            return 1
    src = src.replace(OLD_ANCHOR, NEW_ANCHOR, 1)
    src = src.replace(OLD_MENUBAR, NEW_MENUBAR, 1)
    BUNDLE.write_text(src, encoding="utf-8")
    print("patched", BUNDLE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
