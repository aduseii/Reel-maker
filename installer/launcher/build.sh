#!/usr/bin/env bash
# Builds ReelMaker.exe with MinGW (apt install gcc-mingw-w64-x86-64).
set -euo pipefail
cd "$(dirname "$0")"
cp ../../app/icon.ico icon.ico
x86_64-w64-mingw32-windres launcher.rc -O coff -o launcher.res
x86_64-w64-mingw32-gcc -O2 -municode -mwindows -static -s launcher.c launcher.res -o ReelMaker.exe -lshell32
rm -f launcher.res icon.ico
