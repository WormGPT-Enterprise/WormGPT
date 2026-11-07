import sys, subprocess, re
P='assets/index-CeWFP5bj.js'

def read(): return open(P,encoding='utf-8',errors='replace').read()
def write(s): open(P,'w',encoding='utf-8').write(s)
def check():
    r=subprocess.run(['node','--check',P],capture_output=True,text=True)
    return r.returncode==0, (r.stderr.strip().splitlines()[-1] if r.returncode else '')

def match(s,i0):
    depth=0;i=i0;instr=None;esc=False
    while i<len(s):
        c=s[i]
        if instr:
            if esc:esc=False
            elif c=='\\':esc=True
            elif c==instr:instr=None
        else:
            if c in '"\'`':instr=c
            elif c=='{':depth+=1
            elif c=='}':
                depth-=1
                if depth==0:return i+1
        i+=1
    return -1

def step(name, fn):
    s=read(); s2=fn(s)
    if s2 is None:
        print(f"[skip] {name}: marker not found"); return
    write(s2)
    ok,err=check()
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {len(s)} -> {len(s2)}  {err}")
    if not ok:
        sys.exit(1)

# A) WormCoder generator if-chain -> benign stub
def a(s):
    a1=s.find('let C=[];if(J.includes("keylog")')
    a2=s.find('if(await new Promise(W=>setTimeout(W,800)),B("[✔] Compiling')
    if a1<0 or a2<a1: return None
    stub=('let C=[{id:"ws-safe-1",name:"README.md",language:"markdown",content:"# WormCoder\\n\\n'
          'Code-kit generators (phishing pages, credential harvesters, keyloggers, exploit scripts) were removed from this build."}];')
    return s[:a1]+stub+s[a2:]

# B) Sample Cyber Kits JSX block
def b(s):
    start=s.find('a.jsxs("div",{className:"space-y-1.5",children:[a.jsx("span",{className:"text-[8px] font-bold text-gray-500 uppercase tracking-widest block font-mono",children:"Sample Cyber Kits:"})')
    if start<0: return None
    endmark='},W))]})'; end=s.find(endmark,start)
    if end<0: return None
    end+=len(endmark)
    repl='a.jsx("span",{className:"text-[8px] font-bold text-gray-600 uppercase tracking-widest block font-mono",children:"Code helpers:"})'
    return s[:start]+repl+s[end:]

# C) WF lab suite -> stub
def c(s):
    k=s.find('const WF=({onClose:e,user:t,license:n,chats:r')
    if k<0: return None
    end=match(s, s.find('{', s.find('=>{', k)))
    stub=('const WF=({onClose:e})=>a.jsx("div",{className:"fixed inset-0 z-[60] flex items-center justify-center bg-black text-gray-300 font-mono text-xs p-6",'
          'children:a.jsxs("div",{className:"text-center space-y-3 max-w-md",children:['
          'a.jsx("p",{className:"text-red-400 font-bold",children:"WormLab removed"}),'
          'a.jsx("p",{children:"The offensive security suite (web scanner, SQL auditor, email OSINT, payload store) was stripped from this build."}),'
          'a.jsx("button",{onClick:e,className:"px-3 py-1 rounded bg-red-600 text-white cursor-pointer",children:"Close"})]})})')
    return s[:k]+stub+s[end:]

# D) Email OSINT component HF (remove with leading comma)
def d(s):
    k=s.find(',HF=()=>{')
    if k<0:
        k=s.find('HF=()=>{')
        if k<0: return None
        end=match(s,s.find('{',k)); return s[:k]+s[end:]
    end=match(s,s.find('{',k))
    return s[:k]+s[end:]

step('A WormCoder chain', a)
step('B Cyber Kits', b)
step('C WF lab suite', c)
step('D Email OSINT', d)
