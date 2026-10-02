#!/usr/bin/env bash
# Set up the A/B rig on a Mac: a private copy of a Wineskin engine (CrossOver-based Wine, runs 32-bit DLLs
# through Rosetta), the original DLL, and a tiny freestanding VST2 host built with the system clang.
#   re/ab/setup.sh [/path/to/MeowSynth.dll]      then e.g.  python3 re/ab/t_presets.py
# Needs: Wineskin Winery with an engine downloaded (~/Library/Application Support/Wineskin/Engines),
# Xcode command line tools, python3 with numpy (matplotlib for the plots).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${MEOW_AB_WORK:-$HERE/work}"
DLL="${1:-$HERE/../../../MeowSynth.dll}"
ENGINE="$(ls "$HOME/Library/Application Support/Wineskin/Engines/"*.tar.7z 2>/dev/null | head -1)"
[ -n "$ENGINE" ] || { echo "no Wineskin engine found" >&2; exit 1; }
mkdir -p "$WORK"
[ -d "$WORK/wswine.bundle" ] || tar -xf "$ENGINE" -C "$WORK"
cp "$DLL" "$WORK/MeowSynth.dll"
# the host: no C runtime, linked by pelink.py (the Mac has no Windows linker)
clang -target i686-pc-windows-msvc -ffreestanding -fno-builtin -fno-stack-protector -mno-stack-arg-probe -O1 \
    -c "$HERE/host.c" -o "$WORK/host.obj"
python3 "$HERE/pelink.py" "$WORK/host.obj" "$WORK/host.exe"
WINEPREFIX="$WORK/prefix" WINEDLLOVERRIDES="mscoree,mshtml=" WINEDEBUG=-all "$WORK/wswine.bundle/bin/wine64" cmd /c ver | tail -1
echo "ready: $WORK"
