#!/usr/bin/env python3
"""Pull the original GUI bitmaps out of MeowSynth.dll into assets/ (used by tools/make_art.py).

    re/extract_assets.py /path/to/MeowSynth.dll

The DLL keeps its SynthEdit project in the resource "SE1"/165, lightly scrambled: one byte in three is
XORed with 0x83, and after a scrambled byte whose plain value is odd the next byte is scrambled too.
The skin's PNG files sit in that project as they are."""
import os
import re
import struct
import sys

WANT = {0: "pitchrange", 1: "logo", 2: "polycat", 4: "cat_strip", 5: "lfo", 11: "panels", 16: "knob"}


def se1(dll):
    d = open(dll, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec, opt = struct.unpack_from("<H", d, pe + 6)[0], struct.unpack_from("<H", d, pe + 20)[0]
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        if d[o:o + 5] == b".rsrc":
            va, size, raw = struct.unpack_from("<I", d, o + 12)[0], struct.unpack_from("<I", d, o + 16)[0], struct.unpack_from("<I", d, o + 20)[0]
            break
    else:
        sys.exit("no .rsrc section")

    def walk(off, path):
        named, ids = struct.unpack_from("<HH", d, raw + off + 12)
        for i in range(named + ids):
            name, child = struct.unpack_from("<II", d, raw + off + 16 + i * 8)
            if name & 0x80000000:
                p = raw + (name & 0x7FFFFFFF)
                n = struct.unpack_from("<H", d, p)[0]
                name = d[p + 2:p + 2 + 2 * n].decode("utf-16le")
            if child & 0x80000000:
                r = walk(child & 0x7FFFFFFF, path + [name])
                if r:
                    return r
            elif path and path[0] == "SE1":
                rva, n = struct.unpack_from("<II", d, raw + child)
                return d[rva - va + raw:rva - va + raw + n]
    blob = walk(0, [])
    if not blob:
        sys.exit("no SE1 resource: not a SynthEdit plugin?")
    out, skip = bytearray(blob), 0
    for i in range(len(out)):
        if skip:
            skip -= 1
            continue
        out[i] ^= 0x83
        skip = 0 if out[i] & 1 else 2
    return bytes(out)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    data = se1(sys.argv[1])
    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
    os.makedirs(dest, exist_ok=True)
    for k, m in enumerate(re.finditer(b"\x89PNG\r\n\x1a\n", data)):
        p = m.start() + 8
        while True:
            n, kind = struct.unpack_from(">I4s", data, p)
            p += 12 + n
            if kind == b"IEND":
                break
        if k in WANT:
            open(os.path.join(dest, WANT[k] + ".png"), "wb").write(data[m.start():p])
            print("assets/%s.png" % WANT[k], p - m.start(), "bytes")


if __name__ == "__main__":
    main()
