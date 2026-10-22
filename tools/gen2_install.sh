#!/bin/sh
# Install an mpc-vst-plugins release package (the unzipped -mpc-aarch64.zip) on a Gen2 MPC (MPC Live III and other RK3588
# units) where it can load, and make sure MPC finds its skin. Run on the device, from your computer:
#   scp -r MeowSynth-1.0.2 root@<ip>:/tmp/
#   ssh root@<ip> 'sh -s -- /tmp/MeowSynth-1.0.2' < tools/gen2_install.sh            (installs into /nvme/Synths)
#   ssh root@<ip> 'sh -s -- /tmp/MeowSynth-1.0.2 /some/other/Synths' < tools/gen2_install.sh
# Why not the package's install.sh alone (docs/GEN2_PORTING.md, "Where a plugin can live on Gen2"): its default
# /sdcard/Synths does not exist on Gen2, /synths is read-only, cards and drives under /media are mounted noexec (the .so
# cannot load), and a Synths folder MPC does not list in SynthContentLocations gets MPC's generic page instead of the skin.
# So this checks the target's mount, stops MPC once, adds the folder to SynthContentLocations (MPC.settings backed up
# first), runs the package's install.sh -y -n -t <folder>, and starts MPC again.
# Test hooks (offline only): MPC_INSTALL_TEST=1 skips stopping/starting MPC, MPC_SETTINGS and GEN2_TEST_ARCH override.
set -u
die() { echo "gen2_install: $*" >&2; exit 1; }
PKG="${1:-}"; LOC="${2:-/nvme/Synths}"
[ -n "$PKG" ] || die "usage: sh -s -- <unzipped package folder> [synths folder, default /nvme/Synths]"
case "$LOC" in /*) ;; *) die "the Synths folder must be an absolute path" ;; esac
LOC="${LOC%/}"
[ -f "$PKG/install.sh" ] && [ -f "$PKG/mpc-plugin.json" ] || die "$PKG is not an unzipped release package (no install.sh / mpc-plugin.json)"
[ "${GEN2_TEST_ARCH:-$(uname -m)}" = aarch64 ] || die "this device is $(uname -m), not Gen2: use the -mpc-armv7.zip and its install.sh"
grep -q '"arch": *"aarch64"' "$PKG/mpc-plugin.json" || die "$PKG is not a Gen2 build: use the -mpc-aarch64.zip"
SET="${MPC_SETTINGS:-/data/Settings/MPC/MPC.settings}"
[ -f "$SET" ] || die "$SET not found"

# The mount that holds the folder (the longest mount point on its path; /proc/mounts writes a space as \040) must be
# writable and allow running code. The folder may not exist yet, so its nearest existing parent is checked.
P="$LOC"; while [ ! -d "$P" ]; do P=$(dirname "$P"); done
MNT=$(awk -v p="$(cd "$P" && pwd -P)/" '{
    m = $2; gsub(/\\040/, " ", m); mm = (m == "/") ? "/" : m "/"
    if (index(p, mm) == 1 && length(mm) > best) { best = length(mm); line = m "\t" $3 "\t" $4 }
} END { print line }' /proc/mounts)
MP=$(echo "$MNT" | cut -f1); FS=$(echo "$MNT" | cut -f2); OPTS=$(echo "$MNT" | cut -f3)
echo "target: $LOC (on $MP, $FS, $OPTS)"
case ",$OPTS," in *,ro,*) die "$MP is mounted read-only (on Gen2, /synths is the factory content partition): use /nvme/Synths" ;; esac
case ",$OPTS," in *,noexec,*) die "$MP is mounted noexec, so MPC could not load the plugin from it: use /nvme/Synths" ;; esac
[ "$FS" = tmpfs ] && die "$MP is a RAM disk (tmpfs): the install would vanish at the next reboot. Check the path's spelling and case"
if grep -q '^l' "$PKG/MODES" 2>/dev/null; then
    case "$FS" in exfat|vfat|msdos|ntfs*) die "the package has symlinks and $MP ($FS) cannot hold them" ;; esac
fi
mkdir -p "$LOC" || die "cannot create $LOC"

# MPC's service is acvs on stock firmware, inmusic-mpc on Hakai-enabled systems (as the package's install.sh)
if systemctl cat acvs >/dev/null 2>&1; then SVC=acvs; elif systemctl cat inmusic-mpc >/dev/null 2>&1; then SVC=inmusic-mpc; else SVC=acvs; fi
if [ -z "${MPC_INSTALL_TEST:-}" ]; then
    echo "stopping MPC ($SVC); save your project first"
    systemctl stop "$SVC"
    trap 'systemctl start "$SVC"' EXIT
    i=0; while pidof MPC >/dev/null && [ $i -lt 30 ]; do sleep 1; i=$((i + 1)); done
    pidof MPC >/dev/null && die "MPC did not stop; nothing changed"
fi

# 1. the folder as a skin location (MPC.settings is edited only while MPC is stopped: it saves its own copy over changes)
cp "$SET" "$SET.bak-gen2-$(date +%Y%m%d-%H%M%S)" || die "cannot back up $SET"
if grep -q "<Location>$LOC</Location>" "$SET"; then
    echo "$LOC is already a skin location"
else
    grep -q "</SynthContentLocations>" "$SET" || die "no <SynthContentLocations> list in $SET; settings unchanged"
    awk -v loc="$LOC" '/<\/SynthContentLocations>/ && !done { match($0, /^[ \t]*/); print substr($0, 1, RLENGTH) "  <Location>" loc "</Location>"; done = 1 } { print }' "$SET" > "$SET.new"
    if [ "$(grep -c "<Location>$LOC</Location>" "$SET.new")" = 1 ] && grep -q "</PROPERTIES>" "$SET.new"; then
        mv "$SET.new" "$SET" && echo "added $LOC to MPC's skin locations"
    else
        rm -f "$SET.new"; die "skin location edit failed; settings unchanged"
    fi
fi

# 2. the plugin, with the package's own installer (MPC already stopped: -n)
MPC_SETTINGS="$SET" sh "$PKG/install.sh" -y -n -t "$LOC" || die "the package's install.sh failed (see above); the skin location stays, harmless"

echo "registered: $(grep -o 'file="[^"]*"' "$SET" | grep -F "\"$LOC/" | tr '\n' ' ')"
echo "done: insert the plugin on a track again to see its skin"
