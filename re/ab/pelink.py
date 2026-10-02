#!/usr/bin/env python3
"""Tiny PE32 linker: one i386 COFF object + kernel32 imports -> console exe. Everything goes in one RWX section."""
import struct, sys
obj = open(sys.argv[1], 'rb').read()
mach, nsec, _, symptr, nsym, optsz, _ = struct.unpack_from('<HHIIIHH', obj, 0)
assert mach == 0x14c
strtab = symptr + nsym * 18
def name_of(raw):
    if raw[:4] == b'\0\0\0\0':
        o = strtab + struct.unpack('<I', raw[4:])[0]; return obj[o:obj.index(b'\0', o)].decode()
    return raw.rstrip(b'\0').decode()
secs = []
for i in range(nsec):
    o = 20 + optsz + i * 40
    nm = obj[o:o + 8]; vs, va, rs, rp, relp, _, nrel, _, ch = struct.unpack_from('<IIIIIIHHI', obj, o + 8)
    nm = name_of(nm) if not nm.startswith(b'/') else name_of(b'\0\0\0\0' + struct.pack('<I', int(nm[1:].rstrip(b'\0'))))
    secs.append(dict(name=nm, size=rs, raw=rp, relp=relp, nrel=nrel, ch=ch))
syms = []; i = 0
while i < nsym:
    o = symptr + i * 18
    nm = name_of(obj[o:o + 8]); val, sec, typ, cls, aux = struct.unpack_from('<IhHBB', obj, o + 8)
    syms.append(dict(name=nm, val=val, sec=sec, cls=cls))
    syms += [None] * aux; i += 1 + aux
BASE, SALIGN, FALIGN, SEC_RVA = 0x400000, 0x1000, 0x200, 0x1000
blob = bytearray()
for s in secs:
    s['keep'] = not (s['ch'] & (0x200 | 0x800 | 0x02000000)) and s['size'] > 0
    if not s['keep']: continue
    while len(blob) % 16: blob.append(0)
    s['off'] = len(blob)
    blob += obj[s['raw']:s['raw'] + s['size']] if s['raw'] and not (s['ch'] & 0x80) else bytes(s['size'])
imports = sorted({x['name'] for x in syms if x and x['sec'] == 0 and x['name'].startswith('__imp__')})
# import data: descriptor table, ILT, IAT, names
while len(blob) % 16: blob.append(0)
idt = len(blob); blob += bytes(40)
ilt = len(blob); blob += bytes(4 * (len(imports) + 1))
iat = len(blob); blob += bytes(4 * (len(imports) + 1))
dllname = len(blob); blob += b'KERNEL32.dll\0'
iat_of = {}
for k, imp in enumerate(imports):
    fn = imp[len('__imp__'):].split('@')[0]
    while len(blob) % 2: blob.append(0)
    hn = len(blob); blob += b'\0\0' + fn.encode() + b'\0'
    struct.pack_into('<I', blob, ilt + 4 * k, SEC_RVA + hn); struct.pack_into('<I', blob, iat + 4 * k, SEC_RVA + hn)
    iat_of[imp] = BASE + SEC_RVA + iat + 4 * k
struct.pack_into('<IIIII', blob, idt, SEC_RVA + ilt, 0, 0, SEC_RVA + dllname, SEC_RVA + iat)
def addr(sym):
    if sym['sec'] > 0:
        s = secs[sym['sec'] - 1]
        if not s['keep']: raise SystemExit('symbol %s in dropped section %s' % (sym['name'], s['name']))
        return BASE + SEC_RVA + s['off'] + sym['val']
    if sym['name'] in iat_of: return iat_of[sym['name']]
    raise SystemExit('undefined symbol ' + sym['name'])
for s in secs:
    if not s['keep']: continue
    for r in range(s['nrel']):
        va, si, typ = struct.unpack_from('<IIH', obj, s['relp'] + r * 10)
        loc = s['off'] + va; S = addr(syms[si]); cur = struct.unpack_from('<I', blob, loc)[0]
        if typ == 6: v = cur + S
        elif typ == 0x14: v = cur + S - (BASE + SEC_RVA + loc + 4)
        elif typ == 7: v = cur + S - BASE
        else: raise SystemExit('reloc type %#x' % typ)
        struct.pack_into('<I', blob, loc, v & 0xffffffff)
entry = addr(next(x for x in syms if x and x['name'] == '_entry@0')) - BASE
vsize = len(blob); raw = bytes(blob) + bytes(-len(blob) % FALIGN)
hdr = bytearray(b'MZ' + bytes(58) + struct.pack('<I', 0x40))
hdr += b'PE\0\0' + struct.pack('<HHIIIHH', 0x14c, 1, 0, 0, 0, 224, 0x0103)   # relocs stripped, executable, 32-bit
opt = struct.pack('<HBBIIIIII', 0x10b, 9, 0, len(raw), 0, 0, entry, SEC_RVA, SEC_RVA)
opt += struct.pack('<IIIHHHHHHIIIIHHIIIIII', BASE, SALIGN, FALIGN, 4, 0, 0, 0, 4, 0, 0, SEC_RVA + (vsize + SALIGN - 1) // SALIGN * SALIGN,
                   FALIGN * 2 if False else 0x400, 0, 3, 0, 0x100000, 0x10000, 0x100000, 0x1000, 0, 16)
dirs = [(0, 0)] * 16; dirs[1] = (SEC_RVA + idt, 40); dirs[12] = (SEC_RVA + iat, 4 * (len(imports) + 1))
opt += b''.join(struct.pack('<II', *d) for d in dirs)
assert len(opt) == 224, len(opt)
hdr += opt + b'.all\0\0\0\0' + struct.pack('<IIIIIIHHI', vsize, SEC_RVA, len(raw), 0x400, 0, 0, 0, 0, 0xE00000E0)
hdr += bytes(0x400 - len(hdr))
open(sys.argv[2], 'wb').write(bytes(hdr) + raw)
print('linked', sys.argv[2], len(hdr) + len(raw), 'bytes; imports:', ', '.join(i[7:] for i in imports))
