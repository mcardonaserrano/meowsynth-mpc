# Porting a Gen 1 MPC plugin to Gen 2

A working checklist for taking a plugin built on [mpc-vst-plugins](https://github.com/sd88me/mpc-vst-plugins) for Gen 1
(Force, MPC Live / Live II, One, X, Key: 32-bit ARM) and shipping it for Gen 2 (MPC Live III and other RK3588 units:
64-bit ARM). Written from porting MeowSynth (this repo) on 2026-10-22, and checked on an **MPC Live III, MPC OS 3.9.1**.
Upstream's own design notes are `docs/GEN2.md` and `docs/NOTES.md` in mpc-vst-plugins; this file is the practical path.

How sure each fact is: **[device]** seen on the Live III above, **[offline]** checked on a build machine only,
**[upstream]** taken from mpc-vst-plugins' notes and not re-checked here.

## The short version
1. Rebuild on a current mpc-vst-plugins (section 3 lists what changed under old ports).
2. Build the same sources a second time for aarch64 in `arm64v8/gcc:12-bookworm` (section 4).
3. Run the host test on aarch64 under QEMU (section 5).
4. Package the aarch64 `.so` with `release.py`: same id, uid, version; it makes `<Name>-<ver>-mpc-aarch64.zip` (section 6).
5. Put both zips on the **same** GitHub release; no new catalog entry (section 6).
6. Install on the unit into `/nvme/Synths` and add that folder to MPC's skin locations (section 7; `tools/gen2_install.sh`).
7. Check it on the unit, then add a `tested.json` entry whose device names Gen2 (section 8).

## 1. What is different on Gen 2
| | Gen 1 | Gen 2 |
|---|---|---|
| CPU / userland | armv7 (armhf), 32-bit | aarch64, 64-bit only: a 32-bit `.so` cannot load **[upstream]** |
| glibc | 2.31 build target (MPC OS 2.x has 2.32, 3.x 2.39) | 2.39 (MPC OS 3.x only) **[upstream]**; build on bookworm (2.36) |
| `MPC.settings` | `/media/az01-internal/Settings/MPC/` | `/data/Settings/MPC/MPC.settings` **[device]** |
| MPC service | `acvs` (or `inmusic-mpc` on Hakai) | `acvs` **[device]** |
| Plugin list key in `MPC.settings` | `pluginList-arm` | `pluginList-arm-64bit` **[upstream, device-confirmed by them]** |
| Default Synths folder | `/sdcard/Synths` (internal drive) | none: `/sdcard` is not mounted **[upstream]**; see section 7 |
| Shell | BusyBox | BusyBox v1.36.1: `head -20` is invalid, write `head -n 20` **[device]** |

## 2. Is the code 64-bit clean?
Most wrapper ports are, because the wrapper's VST2 structs use `intptr_t` for pointer-sized fields and the offline host
test already runs on x86_64 **[upstream]**. Things to look for in a port's own code:
- `int` or `int32_t` holding a pointer, `long` assumed to be 4 bytes, `%d`/`%x` printing a `size_t` or pointer.
- A hand-written copy of `AEffect` or another host struct (MeowSynth's `src/meow_test.c` has one; it is laid out with
  `intptr_t` and `void *`, so it is correct on both).
- armv7-only compiler flags (`-mfpu=neon`, `-mfloat-abi=hard`, `-marm`): gcc for aarch64 rejects them. NEON is always
  there on aarch64, so `arm_neon.h` code mostly ports as is; 32-bit inline asm does not.
- Bundled binaries or prebuilt libraries (a Python, `yt-dlp`, a `.a` from another project): each needs an aarch64 copy.
- Hard-coded paths: `/sdcard/...` and `/media/az01-internal/...` do not exist on Gen 2. Use the wrapper's
  `plugin_dir.h` (the folder the `.so` was loaded from) for the plugin's own data.

If the x86_64 host test passes and the aarch64 one (section 5) passes under UBSan, the code is very likely fine.

## 3. Rebuilding an older port on current mpc-vst-plugins
A port last built before 2026-10-21 needs a rebuild anyway (the UpdateDisplay fix: Q-Links on the automation screen;
mpc-vst-plugins discussion 499). Things that broke or changed when MeowSynth went from a 2026-10-02 wrapper to `97a2eff`
**[offline]**:
- **Link with `-lpthread`.** The wrapper now calls `pthread_mutexattr_*`, which glibc 2.31 (the armv7 build image) keeps in
  libpthread: without it the link fails with `undefined reference to pthread_mutexattr_init`. `tools/build_port.sh` already
  has it; a port with its own `build.sh` must add it.
- **`mpc_engine_t` gained `song_pos`** (last field). Engines initialise it positionally, so add a trailing `NULL`; it is
  only called with `"HAS_SONG_POS": 1`.
- **`params.lock`** is written next to `vst.json` on the first `gen_vst.py` run and fails the build if an existing
  parameter changes index. Commit it.
- **Popup option images are now `sh_po_N`**, shared between pickers with the same options, instead of
  `sh_popopt_<t>_<key>_<o>`. A port that post-processes skin images by file name must look the names up in `TUI.json`
  (the `onImage`/`offImage` of the `shPopOpt_<t>_<key>_<o>` button); MeowSynth's `tools/meow_art.py` `theme()` does.
- **Parameter 0 is applied one block late.** MPC's host sets parameter 0 to the far end and back on insert and on every
  STOP; the wrapper now holds a host set of parameter 0 until the next audio block and drops a pair that ends where it
  started. If parameter 0 is a preset, a test that sets it and plays a note in the same block hears the old preset (and a
  preset that switches mono/poly can cut that note). Let one block pass in such a test.
- **Known upstream test failure:** with an option list at parameter 0, `host_test.c` fails `tick 1 steps one option
  (0.000)`, before and after the UpdateDisplay fix: a dropped parameter 0 set leaves `last_pos[0]` stale. A one-line fix
  in `flush_pend0()` (reset `last_pos[0]` and `qacc[0]` when the set is dropped) makes it pass; reported for upstream,
  not part of the wrapper as of `97a2eff`. Treat that single failure as known, not as your port's bug.

## 4. Building for aarch64
- **Ports that use `tools/build_port.sh`:** add `"targets": ["armv7", "aarch64"]` to `vst.json`, then
  `tools/build_port.sh vst.json all`. Output: `build/<so>` (armv7) and `build/aarch64/<so>` **[upstream]**.
- **Ports with their own `build.sh`** (like MeowSynth, which has its own entry point): build the same sources twice with
  the same flags. MeowSynth's `build.sh` is a worked example (`build_so()` and the target loop):

  | Target | Docker image | Platform | glibc ceiling |
  |---|---|---|---|
  | armv7 (Gen 1) | `arm32v7/gcc:11-bullseye` | `linux/arm/v7` | 2.32 for MPC OS 2.x |
  | aarch64 (Gen 2) | `arm64v8/gcc:12-bookworm` | `linux/arm64` | 2.39 |

  Flags: `-O2 -Wall -Wextra -Wno-unused-parameter -fPIC -shared -fvisibility=hidden -std=gnu11 ... -lm -lpthread
  -Wl,--no-undefined`, then `strip`. Check that `VSTPluginMain` is the only exported symbol (`readelf --dyn-syms`) and the
  highest `GLIBC_` version (`readelf -V`). MeowSynth's aarch64 `.so` needs GLIBC_2.34 **[offline]**.
- **Build machine:** Docker must be able to run arm containers. If `docker run --platform linux/arm64 ...` fails with
  `exec /bin/bash: exec format error`, QEMU is not registered: `docker run --privileged --rm tonistiigi/binfmt --install
  arm,arm64`, or install `qemu-user-static` and register `/usr/lib/binfmt.d/qemu-arm.conf` and `qemu-aarch64.conf` through
  `/proc/sys/fs/binfmt_misc/register` (mount `binfmt_misc` first if that folder is empty) **[offline]**.

## 5. Testing before the device
- `tools/test_port.sh vst.json aarch64` runs the host test in an `arm64v8/gcc:12-bookworm` container **[upstream]**.
  UBSan only: ASan's shadow memory does not map under QEMU.
- A port with its own entry point mirrors that: MeowSynth's `./test.sh aarch64` builds `host_test.c` and the port's own
  test with `-fsanitize=undefined -fno-sanitize-recover=undefined` in that container and runs both **[offline]**.
- Expect the same results as on x86_64 (for MeowSynth: identical, including the known failure in section 3).

## 6. Packaging and the catalog
- Run `release.py` once per `.so` with the **same** `--version`, `--id`, `--repo`, `--license`. It reads the ELF machine
  and names the zip `-mpc-armv7.zip` or `-mpc-aarch64.zip`; the manifest's `arch` says which, `os_compat` is `["3.x"]`
  for aarch64 **[offline]**.
- Check each zip: `tools/catalog_check.py <zip> --catalog --expect-id <id> --expect-repo <owner/repo>`.
- Attach **both** zips to the **same** GitHub release (one tag). Do not add a second catalog entry: the catalog finds the
  aarch64 zip by swapping `armv7` for `aarch64` in the entry's `asset_pattern`, and it must match the armv7 zip's version
  and uid **[upstream]**. A listed plugin needs no catalog PR for a new release; it is picked up nightly.
- The zip's `INSTALL.md` (written by `release.py`) still describes Gen 1 devices only; the installer itself handles
  aarch64 (it checks `uname -m` against the manifest and registers under `pluginList-arm-64bit`) **[device]**.

## 7. Where a plugin can live on Gen 2 (MPC Live III, MPC OS 3.9.1) **[device]**
`grep -E "synths|nvme|/media" /proc/mounts` on the unit:

| Path | What it is | Usable? |
|---|---|---|
| `/synths` | NVMe partition 1, `MPC_Content`, exFAT, **`ro`** (factory content) | No: read-only all the time, MPC running or not |
| `/nvme` | NVMe partition 2, `MPC_User`, exFAT, `rw`, no `noexec` | **Yes: install into `/nvme/Synths`** |
| `/media` | a **tmpfs** (RAM) holding the drives' mount points | No: anything written here directly vanishes at reboot |
| `/media/<label>` | SD cards, USB/SSD drives: exFAT, `rw,nosuid,nodev,noexec,nosymfollow` | No: `noexec`, so MPC cannot `dlopen` a `.so` there |
| `/sdcard` | not mounted | No: the package installer's default target |

Traps seen on the way:
- **Case matters in `/media`.** The card was `/media/MPC-SD`; `install.sh -t /media/MPC-sd/Synths` created a new folder
  in the tmpfs instead of on the card. The plugin even loaded (the tmpfs is not `noexec`) but it would have vanished at
  reboot, and MPC showed the card as "MPC-sd 2" next to the stray folder. Clean-up: `uninstall.sh -t <that folder>`,
  then `rmdir` the stray folders.
- **`noexec` cards:** the plugin installs but cannot load. Remounting the card `exec` works only until the card is
  re-inserted or the unit reboots, and Gen 2's root filesystem is read-only, so a boot-time fix has no obvious home.
  `/nvme` avoids all of this.
- **exFAT holds no symlinks** (both `/nvme` and the cards): a package whose `MODES` file lists symlinks cannot be
  installed there as is.

**The skin needs the folder in `SynthContentLocations`.** MPC looks for `<vendor> - VST - <name>/Plugin Skins/` only in
the folders listed in `MPC.settings` under `<SynthContentLocations>` (on the unit above: the two drives' `Synths`,
`/synths/Expansions`, `/synths/Synths`, `/usr/share/Akai/Content/Synths`; not `/nvme/Synths`). A plugin outside them
loads and plays but shows **MPC's generic page (a row of knobs and "Screen 1 / 2")**. Add
`<Location>/nvme/Synths</Location>` to that list with MPC stopped (MPC saves its own copy of `MPC.settings` over edits
made while it runs), back the file up first, then remove and re-insert the plugin on the track. MPC kept the added
location across its restart **[device]**; across a full reboot is not checked yet.

**`tools/gen2_install.sh` does all of the above** for any mpc-vst-plugins aarch64 package: it refuses a read-only,
`noexec` or tmpfs target (and symlinks on exFAT), stops MPC once, backs up `MPC.settings`, adds the folder to
`SynthContentLocations`, runs the package's `install.sh -y -n -t <folder>`, and starts MPC again:
```
unzip <Name>-<ver>-mpc-aarch64.zip && scp -r <Name>-<ver> root@<ip>:/tmp/
ssh root@<ip> 'sh -s -- /tmp/<Name>-<ver>' < tools/gen2_install.sh        # default target /nvme/Synths
```
Checked offline against a fake device (install, re-run, replacing an old entry with the same uid, each refusal leaving
`MPC.settings` untouched) **[offline]**; the same steps by hand worked on the Live III **[device]**.

## 8. On the device, and recording it
Check, with the Gen 2 build installed:
- MeowSynth (your plugin) appears in the plugin browser under Instrument plugins, inserts and plays.
- Its skin shows (not the generic page), Q-Links follow the page, and Q-Links move parameters on track edit ->
  automation (the UpdateDisplay fix).
- Presets, saving and reopening a project; ideally a project opened on the other generation.
- CPU: `tools/bench.sh` is armv7 only for now; watch MPC's CPU meter in a busy project instead.

Then add a `tested.json` entry at the repo root. The catalog counts it as a Gen 2 test only when the device names Gen2,
and only for a version whose release has an aarch64 zip (it then shows "Verified Gen2"):
```json
[ { "version": "1.0.2", "device": "MPC Live III (Gen2)", "firmware": "3.9.1", "date": "2026-10-22" } ]
```

## 9. Open questions
- Does `/nvme/Synths` in `SynthContentLocations` survive a full reboot and an MPC OS update?
- Is `/nvme` mounted the same way on other Gen 2 models and later MPC OS versions? Check `/proc/mounts` first.
- A durable way to make a card's `Synths` folder executable on Gen 2 (Gen 1 has upstream's drive exec patch).
- An aarch64 `bench.c`.
