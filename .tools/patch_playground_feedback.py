#!/usr/bin/env python3
"""Make the Playground's "Run Request" explain itself when it does nothing.

The upstream handler starts with ``if(!u.trim())return;`` — clicking the
button with an empty prompt is a silent no-op, so the page looks broken.
This patch replaces that bare return with a visible message.

Run after the other bundle patches. Idempotent: running it twice is a no-op.
"""
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent / "site" / "assets" / "index-CeWFP5bj.js"

MARKER = "Enter a prompt, then click Run Request."

OLD = "Q=async()=>{var Ce,he,je,Ee,De,Pe,Fe,k;if(!u.trim())return;if(!t){"
NEW = ("Q=async()=>{var Ce,he,je,Ee,De,Pe,Fe,k;"
       'if(!u.trim()){_("Enter a prompt, then click Run Request.");return}if(!t){')


def main():
    src = BUNDLE.read_text(encoding="utf-8")
    if MARKER in src:
        print("already patched")
        return 0
    if src.count(OLD) != 1:
        print(f"anchor not unique ({src.count(OLD)})", file=sys.stderr)
        return 1
    BUNDLE.write_text(src.replace(OLD, NEW, 1), encoding="utf-8")
    print("patched", BUNDLE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
