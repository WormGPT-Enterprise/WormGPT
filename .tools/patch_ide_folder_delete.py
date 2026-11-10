#!/usr/bin/env python3
"""Add folder deletion to the Worm IDE explorer.

The upstream bundle only offers a per-file trash icon and a per-folder ZIP
export, so a folder can never be removed. This script wires two affordances
into the IDE component:

* a trash icon on each folder row, revealed on hover, which asks for a second
  click before it deletes the folder together with every file inside it;
* a File -> Delete Folder entry acting on the folder currently selected in the
  explorer (disabled for the built-in "Agent Project").

Run after patch_ide_menu.py. Idempotent: running it twice is a no-op.
"""
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent / "site" / "assets" / "index-CeWFP5bj.js"

MARKER = "[ZqDel,setZqDel]"

STATE_OLD = "})=>{var Le;const[m,g]=v.useState(240)"
STATE_NEW = "})=>{var Le;const[ZqDel,setZqDel]=v.useState(null);const[m,g]=v.useState(240)"

ROW_OLD = (
    'className:`w-full h-7 px-2 flex items-center gap-1.5 text-left text-[11px] '
    '${$===L?"bg-sky-500/10 text-sky-100":"text-zinc-300 hover:bg-white/[0.04]"}`,children:['
)
ROW_NEW = (
    'className:`group w-full h-7 px-2 flex items-center gap-1.5 text-left text-[11px] '
    '${$===L?"bg-sky-500/10 text-sky-100":"text-zinc-300 hover:bg-white/[0.04]"}`,children:['
    'a.jsx("span",{role:"button",title:ZqDel===L?"Click again to delete folder and its files":`Delete ${L}`,'
    'onClick:Se=>{Se.stopPropagation(),ZqDel===L?(ee(ae=>ae.filter(qe=>qe!==L)),'
    't(ae=>ae.filter(qe=>(qe.projectName||"Workspace")!==L)),'
    'i(ae=>ae.filter(qe=>{const Nt=e.find(st=>st.id===qe);return !Nt||(Nt.projectName||"Workspace")!==L})),'
    'setZqDel(null),$===L&&q("Agent Project"),K(ae=>[...ae,`Deleted folder ${L}`])):setZqDel(L)},'
    'className:`p-0.5 ${ZqDel===L?"text-red-400":"opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-300"}`,'
    'children:a.jsx(pa,{className:"w-3 h-3"})}),'
)

MENU_OLD = 'item("Close Editor","",P.onClose,!P.onClose)])'
MENU_NEW = (
    'item("Close Editor","",P.onClose,!P.onClose),'
    'item("Delete Folder","",P.onDeleteFolder,!P.hasActiveFolder)])'
)

PROPS_OLD = "onDownloadFile:re,onExportZip:()=>ke(),onClose:o,editorRef:ln,"
PROPS_NEW = (
    "onDownloadFile:re,onExportZip:()=>ke(),onClose:o,editorRef:ln,"
    'hasActiveFolder:$!=="Agent Project",'
    'onDeleteFolder:()=>{const _f=$;ee(ae=>ae.filter(qe=>qe!==_f)),'
    't(ae=>ae.filter(qe=>(qe.projectName||"Workspace")!==_f)),'
    'i(ae=>ae.filter(qe=>{const Nt=e.find(st=>st.id===qe);return !Nt||(Nt.projectName||"Workspace")!==_f})),'
    '$===_f&&q("Agent Project"),K(ae=>[...ae,`Deleted folder ${_f}`])},'
)


def main():
    src = BUNDLE.read_text(encoding="utf-8")
    if MARKER in src:
        print("already patched")
        return 0
    for old in (STATE_OLD, ROW_OLD, MENU_OLD, PROPS_OLD):
        if src.count(old) != 1:
            print(f"anchor not unique: {old[:60]!r} ({src.count(old)})", file=sys.stderr)
            return 1
    src = src.replace(STATE_OLD, STATE_NEW, 1)
    src = src.replace(ROW_OLD, ROW_NEW, 1)
    src = src.replace(MENU_OLD, MENU_NEW, 1)
    src = src.replace(PROPS_OLD, PROPS_NEW, 1)
    BUNDLE.write_text(src, encoding="utf-8")
    print("patched", BUNDLE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
