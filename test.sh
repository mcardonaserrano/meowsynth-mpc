#!/usr/bin/env bash
# Offline test on this machine, before anything goes to a device: mpc-vst-plugins' host test
# (tools/host_test.c: instances, parameters, options, popup, note -> audio, chunk) against this port's
# own entry point, under ASan/UBSan, then the cat check (src/meow_test.c).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MV="$(cd "${MPC_VST:-$HERE/../mpc-vst-plugins}" && pwd)"
CC="${CC:-cc}"
cd "$HERE"
mkdir -p build
python3 "$MV/tools/gen_vst.py" vst.json --params-h
SAN="-fsanitize=address,undefined -fno-omit-frame-pointer -g -O1"
$CC $SAN -std=gnu11 -Ibuild -I"$MV/wrapper" "$MV/tools/host_test.c" src/meow_engine.c src/meow_vst.c -lm -o build/host_test
build/host_test
$CC $SAN -std=gnu11 -Ibuild -I"$MV/wrapper" src/meow_test.c src/meow_engine.c src/meow_vst.c -lm -o build/meow_test
build/meow_test
