#!/usr/bin/env python3
"""Teach the Worm IDE about more languages.

The shipped bundle recognises only 20 extensions (and gives several of them
no starter content), so a new .cpp/.ts/.go file opens with no highlighting
entry and an empty buffer. This widens the extension table and adds starter
templates for the languages the backend runner can execute.

Run after patch_ide_menu.py and patch_ide_folder_delete.py. Idempotent.
"""
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent / "site" / "assets" / "index-CeWFP5bj.js"

MARKER = 'txt:"text"}[t||""]||"text"}'

PA_OLD = (
    'PA=e=>{var r;const t=(r=e.split(".").pop())==null?void 0:r.toLowerCase();return{'
    'html:"html",htm:"html",css:"css",js:"javascript",jsx:"jsx",ts:"typescript",tsx:"tsx",'
    'py:"python",php:"php",sql:"sql",cpp:"cpp",c:"c",h:"c",sh:"bash",json:"json",'
    'md:"markdown",yml:"yaml",yaml:"yaml",go:"go",rs:"rust",java:"java"}[t||""]||"text"}'
)
PA_NEW = (
    'PA=e=>{var r;const t=(r=e.split(".").pop())==null?void 0:r.toLowerCase();return{'
    'html:"html",htm:"html",css:"css",scss:"scss",less:"less",'
    'js:"javascript",mjs:"javascript",cjs:"javascript",jsx:"jsx",ts:"typescript",tsx:"tsx",'
    'py:"python",php:"php",sql:"sql",cpp:"cpp",cc:"cpp",cxx:"cpp",hpp:"cpp",h:"c",c:"c",'
    'sh:"bash",bash:"bash",zsh:"bash",json:"json",md:"markdown",yml:"yaml",yaml:"yaml",'
    'go:"go",rs:"rust",java:"java",rb:"ruby",kt:"kotlin",swift:"swift",lua:"lua",'
    'toml:"toml",xml:"xml",vue:"vue",cs:"csharp",txt:"text"}[t||""]||"text"}'
)

TEMPLATES_OLD = '`:t==="markdown"?`# ${e.replace(/\\.[^.]+$/,"")}\n'
TEMPLATES_NEW = (
    '`:t==="javascript"?`console.log("Hello from Worm IDE");\n'
    '`:t==="typescript"?`const greet = (name: string): string => \\`Hello, ${name}!\\`;\\n\\n'
    'console.log(greet("Worm IDE"));\\n'
    '`:t==="cpp"?`#include <iostream>\\n\\nint main() {\\n'
    '    std::cout << "Hello from Worm IDE" << std::endl;\\n    return 0;\\n}\\n'
    '`:t==="c"?`#include <stdio.h>\\n\\nint main(void) {\\n'
    '    printf("Hello from Worm IDE\\\\n");\\n    return 0;\\n}\\n'
    '`:t==="bash"?`#!/usr/bin/env bash\\nset -euo pipefail\\n\\n'
    'echo "Hello from Worm IDE"\\n'
    '`:t==="go"?`package main\\n\\nimport "fmt"\\n\\nfunc main() {\\n'
    '    fmt.Println("Hello from Worm IDE")\\n}\\n'
    '`:t==="rust"?`fn main() {\\n    println!("Hello from Worm IDE");\\n}\\n'
    '`:t==="php"?`<?php\\n\\necho "Hello from Worm IDE\\\\n";\\n'
    '`:t==="ruby"?`puts "Hello from Worm IDE"\\n'
    '`:t==="lua"?`print("Hello from Worm IDE")\\n'
    '`:t==="csharp"?`using System;\\n\\nclass Program {\\n'
    '    static void Main() {\\n        Console.WriteLine("Hello from Worm IDE");\\n'
    '    }\\n}\\n'
    '`:t==="java"?`public class Main {\\n    public static void main(String[] args) {\\n'
    '        System.out.println("Hello from Worm IDE");\\n    }\\n}\\n'
    '`:t==="sql"?`-- Worm IDE SQL scratchpad\\nSELECT 1 AS ok;\\n'
    '`:t==="yaml"?`name: worm-ide\\nversion: 1\\n'
    '`:t==="xml"?`<?xml version="1.0" encoding="UTF-8"?>\\n<root>Hello from Worm IDE</root>\\n'
    '`:t==="markdown"?`# ${e.replace(/\\.[^.]+$/,"")}\n'
)


def main():
    src = BUNDLE.read_text(encoding="utf-8")
    if MARKER in src:
        print("already patched")
        return 0
    for old in (PA_OLD, TEMPLATES_OLD):
        if src.count(old) != 1:
            print(f"anchor not unique: {old[:60]!r} ({src.count(old)})", file=sys.stderr)
            return 1
    src = src.replace(PA_OLD, PA_NEW, 1).replace(TEMPLATES_OLD, TEMPLATES_NEW, 1)
    BUNDLE.write_text(src, encoding="utf-8")
    print("patched", BUNDLE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
