#!/usr/bin/env bash
# Build MeowSynth for MPC OS: page art -> skin -> themed skin -> the armhf plugin -> the plugin folder.
#   ./build.sh            (needs Docker; MPC_VST = a checkout of sd88me/mpc-vst-plugins, default ../mpc-vst-plugins)
# Output: build/meowsynth.so, and dist/"knobster - VST - MeowSynth"/ ready for /sdcard/Synths.
# This port has its own entry point (src/meow_vst.c) so it cannot go through tools/build_port.sh, which
# always links the stock wrapper; the steps and compiler flags below are that script's.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MV="$(cd "${MPC_VST:-$HERE/../mpc-vst-plugins}" && pwd)"
U="$(id -u):$(id -g)"
SKIN="knobster - VST - MeowSynth"
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

# 2. the plugin: armhf, glibc 2.31 (bullseye), only VSTPluginMain exported
docker run --rm --platform linux/arm/v7 -u "$U" -v "$HERE":/b -v "$MV":/mv:ro -w /b arm32v7/gcc:11-bullseye bash -euc "
  gcc -O2 -Wall -Wextra -Wno-unused-parameter -fPIC -shared -fvisibility=hidden -std=gnu11 -Ibuild -I/mv/wrapper \
      src/meow_engine.c src/meow_vst.c -lm -Wl,--no-undefined -o build/meowsynth.so
  strip build/meowsynth.so
  echo \"exported: \$(readelf --dyn-syms -W build/meowsynth.so | grep -E ' GLOBAL .* [0-9]+ [A-Za-z]' | grep -v UND | awk '{print \$8}' | tr '\n' ' ')\"
  echo \"highest glibc: \$(readelf -V build/meowsynth.so | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -1) (MPC OS 2.x has 2.32)\"
"

# 3. the plugin folder (skin + .so in one place), and the same as a zip with mpc-vst-plugins' installer
rm -rf "dist/$SKIN" dist/MeowSynth-*-mpc-armv7.zip
mkdir -p dist
cp -R "build/skin/$SKIN" "dist/$SKIN"
cp build/meowsynth.so "dist/$SKIN/"
python3 "$MV/tools/release.py" --so build/meowsynth.so --skin "build/skin/$SKIN" --entry build/pluginlist-entry.xml \
    --version "$VERSION" --about "knobster's MeowSynth, rebuilt natively for MPC OS." -o dist
echo "plugin folder: dist/$SKIN"
