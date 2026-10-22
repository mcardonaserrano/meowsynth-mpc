#!/usr/bin/env bash
# Build MeowSynth for MPC OS: page art -> skin -> themed skin -> the plugin, once per CPU -> the plugin folder and zips.
#   ./build.sh [armv7|aarch64|all]   (default all; needs Docker with QEMU for arm/v7 and arm64; MPC_VST = a checkout of
#                                     sd88me/mpc-vst-plugins, default ../mpc-vst-plugins)
# armv7 is Gen1 (MPC Live/One/X/Key, Force), aarch64 is Gen2 (MPC Live III and other RK3588 units: 64-bit only, docs/GEN2.md there).
# Output: build/meowsynth.so (armv7), build/aarch64/meowsynth.so, dist/"knobster - VST - MeowSynth"/ (the armv7 plugin
# folder, ready for /sdcard/Synths), and dist/MeowSynth-<version>-mpc-armv7.zip / -mpc-aarch64.zip for the one release.
# This port has its own entry point (src/meow_vst.c) so it cannot go through tools/build_port.sh, which
# always links the stock wrapper; the steps and compiler flags below are that script's.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MV="$(cd "${MPC_VST:-$HERE/../mpc-vst-plugins}" && pwd)"
U="$(id -u):$(id -g)"
SKIN="knobster - VST - MeowSynth"
TARGETS="${1:-all}"; [ "$TARGETS" = all ] && TARGETS="armv7 aarch64"
cd "$HERE"
VERSION="$(cat VERSION)"   # shown on the panel and used for the zip
[ -f assets/panels.png ] || { echo "assets/ is empty: run re/extract_assets.py /path/to/MeowSynth.dll first" >&2; exit 1; }
mkdir -p build

# 1. artwork, params.h, skin (browser renderer), then the MeowSynth finish on top
docker build -q -t mpc-vst-html-art "$MV/tools/html_art" >/dev/null
docker run --rm -u "$U" -e HOME=/tmp -e MPC_VST=/mv -v "$HERE":/w -v "$MV":/mv:ro -w /w mpc-vst-html-art sh -euc "
  python3 tools/meow_art.py images
  python3 /mv/tools/gen_vst.py vst.json
  python3 tools/meow_art.py theme 'build/skin/$SKIN/Plugin Skins'
"

# 2. the plugin, only VSTPluginMain exported: armhf with glibc 2.31 (bullseye) so it also loads on MPC OS 2.x (2.32);
#    aarch64 with bookworm (2.36), as Gen2 only runs MPC OS 3.x (2.39)
build_so() {   # build_so <image> <docker platform> <output .so> <glibc note>
  mkdir -p "$(dirname "$3")"
  docker run --rm --platform "$2" -u "$U" -v "$HERE":/b -v "$MV":/mv:ro -w /b "$1" bash -euc "
    gcc -O2 -Wall -Wextra -Wno-unused-parameter -fPIC -shared -fvisibility=hidden -std=gnu11 -Ibuild -I/mv/wrapper \
        src/meow_engine.c src/meow_vst.c -lm -lpthread -Wl,--no-undefined -o $3
    strip $3
    echo \"$3 exported: \$(readelf --dyn-syms -W $3 | grep -E ' GLOBAL .* [0-9]+ [A-Za-z]' | grep -v UND | awk '{print \$8}' | tr '\n' ' ')\"
    echo \"$3 highest glibc: \$(readelf -V $3 | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -1) ($4)\"
  "
}
for t in $TARGETS; do
  case $t in
    armv7)   build_so arm32v7/gcc:11-bullseye linux/arm/v7 build/meowsynth.so "MPC OS 2.x has 2.32" ;;
    aarch64) build_so arm64v8/gcc:12-bookworm linux/arm64 build/aarch64/meowsynth.so "Gen2 MPC OS 3.x has 2.39" ;;
    *) echo "unknown target $t (armv7, aarch64 or all)" >&2; exit 1 ;;
  esac
done

# 3. the plugin folder (skin + armv7 .so in one place), and a zip per CPU with mpc-vst-plugins' installer
#    (release.py names it from the .so: -mpc-armv7.zip or -mpc-aarch64.zip; both go on the same release)
mkdir -p dist
for t in $TARGETS; do
  case $t in
    armv7)   SO=build/meowsynth.so
             rm -rf "dist/$SKIN" && cp -R "build/skin/$SKIN" "dist/$SKIN" && cp "$SO" "dist/$SKIN/"
             echo "plugin folder: dist/$SKIN" ;;
    aarch64) SO=build/aarch64/meowsynth.so ;;
  esac
  rm -f dist/MeowSynth-*-mpc-$t.zip
  python3 "$MV/tools/release.py" --so "$SO" --skin "build/skin/$SKIN" --entry build/pluginlist-entry.xml \
      --version "$VERSION" --about "knobster's MeowSynth, rebuilt natively for MPC OS." \
      --repo mcardonaserrano/meowsynth-mpc --license MIT --id meowsynth -o dist
done
