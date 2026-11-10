#!/usr/bin/env bash
# Install the language runtimes the IDE Run button can execute.
#
# The container's apt layer is not persisted across restarts, so rerun this
# after a restart (or before a demo) to restore PHP, Ruby, Go, Rust, Java,
# Lua and C#. Python, Node, GCC/G++ and Bash ship with the image.
set -u

PKGS="php-cli ruby golang-go rustc default-jdk-headless lua5.4 mono-devel"

missing=""
for bin in php ruby go rustc javac lua5.4 mcs; do
  command -v "$bin" >/dev/null 2>&1 || missing="$missing $bin"
done

if [ -z "$missing" ]; then
  echo "all runtimes already present"
  exit 0
fi
echo "missing:$missing -> installing:$PKGS"
sudo apt-get update -q
sudo apt-get install -y -q $PKGS
echo "--- versions ---"
for c in "python3 --version" "node --version" "gcc --version" "g++ --version" "php --version" \
         "ruby --version" "go version" "rustc --version" "javac -version" "lua5.4 -v" "mcs --version"; do
  printf '%-16s ' "${c%% *}"
  $c 2>&1 | head -1
done
