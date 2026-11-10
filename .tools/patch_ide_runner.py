#!/usr/bin/env python3
"""Make the Worm IDE Run button execute code, and preview CSS.

Upstream, Run only previews HTML; every other language answers "other runtimes
require a sandbox service" and nothing happens. This script points Run at the
backend runner (POST /api/run) and renders a stylesheet preview document so the
Preview tab is useful for CSS too.

Run after patch_ide_languages.py. Idempotent.
"""
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent / "site" / "assets" / "index-CeWFP5bj.js"

MARKER = "ZqPreview="

RUN_OLD = (
    ',Me=()=>{A(!0),z((Xe==null?void 0:Xe.language)==="html"?"preview":"terminal"),'
    '(Xe==null?void 0:Xe.language)!=="html"&&K(L=>[...L,`Run requested for '
    '${(Xe==null?void 0:Xe.name)||"workspace"}. Browser execution supports HTML preview; '
    'other runtimes require a sandbox service.`])};'
)
RUN_NEW = (
    ',Me=async()=>{A(!0);const _lg=Xe==null?void 0:Xe.language;'
    'if(_lg==="html"||_lg==="css"){z("preview");return}z("terminal");'
    'if(!_lg){K(L=>[...L,"Open a file to run."]);return}'
    'const _fs=(Xt&&Xt.length?Xt:e).map(f=>({name:f.name,content:f.content}));'
    'K(L=>[...L,`$ Running ${Xe.name} ...`]);'
    'try{const _r=await fetch("/api/run",{method:"POST",'
    'headers:{"Content-Type":"application/json",'
    'Authorization:"Bearer "+(localStorage.getItem("sessionToken")||"")},'
    'body:JSON.stringify({files:_fs,entry:Xe.name})});'
    'const _d=await _r.json();'
    'if(_d.error){K(L=>[...L,"! "+_d.error]);return}'
    'const _o=((_d.stdout||"")+(_d.stderr||"")).replace(/\\n$/,"");'
    'K(L=>[...L,...(_o?_o.split("\\n"):[]),'
    '(_d.ok?"OK ":"FAIL ")+(_d.language||"")+" exited with code "+_d.exitCode]);'
    '}catch(_e){K(L=>[...L,"Run failed: "+(_e&&_e.message||_e)])}};'
)

PREVIEW_OLD = 'Xn=typeof(Xe==null?void 0:Xe.content)=="string"?Xe.content:"",Ra=Xn.length>6e4'
PREVIEW_NEW = (
    'Xn=typeof(Xe==null?void 0:Xe.content)=="string"?Xe.content:"",'
    'ZqPreview=Xn&&(Xe==null?void 0:Xe.language)==="css"?'
    '`<!doctype html><html><head><meta charset="UTF-8" /><style>${Xn}</style></head>'
    '<body><h1>CSS preview</h1><p>This page renders your stylesheet.</p>'
    '<button>Sample button</button></body></html>`:Xn,'
    'Ra=Xn.length>6e4'
)

IFRAME_OLD = ('E==="preview"&&(Xe==null?void 0:Xe.language)==="html"&&ba!==Xe.name'
              '?a.jsx("iframe",{title:"Project preview",srcDoc:Xn,')
IFRAME_NEW = ('E==="preview"&&["html","css"].includes(Xe==null?void 0:Xe.language)&&ba!==Xe.name'
              '?a.jsx("iframe",{title:"Project preview",srcDoc:ZqPreview,')


def main():
    src = BUNDLE.read_text(encoding="utf-8")
    if MARKER in src:
        print("already patched")
        return 0
    for old in (RUN_OLD, PREVIEW_OLD, IFRAME_OLD):
        if src.count(old) != 1:
            print(f"anchor not unique: {old[:60]!r} ({src.count(old)})", file=sys.stderr)
            return 1
    src = (src.replace(RUN_OLD, RUN_NEW, 1)
              .replace(PREVIEW_OLD, PREVIEW_NEW, 1)
              .replace(IFRAME_OLD, IFRAME_NEW, 1))
    BUNDLE.write_text(src, encoding="utf-8")
    print("patched", BUNDLE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
