#!/usr/bin/env bash
# Offline test on this machine, before anything goes to a device: mpc-vst-plugins' host test
# (tools/host_test.c: instances, parameters, options, popup, note -> audio, chunk) against this port's
# own entry point, under ASan/UBSan, then the cat check (src/meow_test.c).
#   ./test.sh            on this machine
#   ./test.sh aarch64    the same in an arm64 container (Gen2's CPU; needs Docker with QEMU), UBSan only: ASan's
#                        shadow memory does not map under QEMU (as mpc-vst-plugins' tools/test_port.sh)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MV="$(cd "${MPC_VST:-$HERE/../mpc-vst-plugins}" && pwd)"
CC="${CC:-cc}"
cd "$HERE"
mkdir -p build
python3 "$MV/tools/gen_vst.py" vst.json --params-h
if [ "${1:-}" = aarch64 ]; then
  docker run --rm --platform linux/arm64 -u "$(id -u):$(id -g)" -v "$HERE":/b -v "$MV":/mv:ro -w /b arm64v8/gcc:12-bookworm bash -euc '
    SAN="-fsanitize=undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer -g -O1"
    gcc $SAN -std=gnu11 -Ibuild -I/mv/wrapper /mv/tools/host_test.c src/meow_engine.c src/meow_vst.c -lm -lpthread -o build/host_test.aarch64
    build/host_test.aarch64
    gcc $SAN -std=gnu11 -Ibuild -I/mv/wrapper src/meow_test.c src/meow_engine.c src/meow_vst.c -lm -lpthread -o build/meow_test.aarch64
    build/meow_test.aarch64
  '
  exit
fi
SAN="-fsanitize=address,undefined -fno-omit-frame-pointer -g -O1"
$CC $SAN -std=gnu11 -Ibuild -I"$MV/wrapper" "$MV/tools/host_test.c" src/meow_engine.c src/meow_vst.c -lm -o build/host_test
build/host_test
$CC $SAN -std=gnu11 -Ibuild -I"$MV/wrapper" src/meow_test.c src/meow_engine.c src/meow_vst.c -lm -o build/meow_test
build/meow_test
