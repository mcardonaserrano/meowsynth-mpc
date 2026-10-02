#!/usr/bin/env python3
"""Walk the MFC CArchive object graph of the SynthEdit project inside MeowSynth.dll (see re/NOTES.md)."""
import os, struct, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_assets  # noqa: E402

# the DLL: $MEOW_DLL, or MeowSynth.dll next to the port's folder
DLL = os.environ.get('MEOW_DLL') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'MeowSynth.dll')
o = extract_assets.se1(DLL)
START = o.index(b'\xff\xff\x5f\x00\x0a\x00CContainer')
BASE_IDX = 0x3a          # calibrated: CContainer's class index (later refs are 0x803a)


class Stop(Exception):
    pass


class R:
    def __init__(self):
        self.p = START
        self.next = BASE_IDX
        self.classes = {}    # idx -> name
        self.objs = {}       # idx -> dict
        self.depth = 0

    def u8(self):
        v = o[self.p]; self.p += 1; return v

    def u16(self):
        v = struct.unpack_from('<H', o, self.p)[0]; self.p += 2; return v

    def u32(self):
        v = struct.unpack_from('<I', o, self.p)[0]; self.p += 4; return v

    def i32(self):
        v = struct.unpack_from('<i', o, self.p)[0]; self.p += 4; return v

    def f64(self):
        v = struct.unpack_from('<d', o, self.p)[0]; self.p += 8; return v

    def f32(self):
        v = struct.unpack_from('<f', o, self.p)[0]; self.p += 4; return v

    def raw(self, n):
        v = o[self.p:self.p + n]; self.p += n; return v

    def s(self):
        if o[self.p:self.p + 3] != b'\xff\xfe\xff':
            raise Stop('expected CString at %x: %s' % (self.p, o[self.p:self.p + 24].hex()))
        self.p += 3
        n = self.u8()
        if n == 0xff:
            n = self.u16()
        v = o[self.p:self.p + 2 * n].decode('utf-16le'); self.p += 2 * n
        return v

    def peek_s(self):
        return o[self.p:self.p + 3] == b'\xff\xfe\xff'

    def obj(self):
        """CArchive::ReadObject: returns the object's index (or None)."""
        tag = self.u16()
        if tag == 0:
            return None
        if tag == 0xffff:
            schema = self.u16(); ln = self.u16(); name = self.raw(ln).decode()
            ci = self.next; self.next += 1
            self.classes[ci] = name
            cls = name
        elif tag & 0x8000:
            ci = tag & 0x7fff
            if ci not in self.classes:
                raise Stop('unknown class ref %x at %x' % (ci, self.p - 2))
            cls = self.classes[ci]
        else:
            if tag not in self.objs:
                raise Stop('ref to unknown object %x at %x' % (tag, self.p - 2))
            return tag
        oi = self.next; self.next += 1
        d = {'id': oi, 'cls': cls, 'at': self.p}
        self.objs[oi] = d
        self.depth += 1
        h = HANDLERS.get(cls)
        if h is None:
            raise Stop('no handler for class %s at %x: %s' % (cls, self.p, o[self.p:self.p + 64].hex()))
        h(self, d)
        self.depth -= 1
        return oi


def plug_base(r, d):
    d['idx'] = r.u16()
    d['default'] = r.s()
    n = r.u16()
    d['lines'] = [r.obj() for _ in range(n)]


def h_plug2(r, d):
    plug_base(r, d)


def h_plugio(r, d):
    plug_base(r, d)
    d['name'] = r.s()
    d['dir'] = r.u16()
    d['partner'] = r.obj()
    d['dtype'] = r.u16()


def h_plugfeature(r, d):
    plug_base(r, d)
    d['a'] = r.u32(); d['dtype'] = r.u32(); d['fid'] = r.u32()
    d['name'] = r.s(); d['list'] = r.s(); d['flags'] = r.u32()


def h_line(r, d):
    d['type'] = r.s()
    d['from'] = r.obj()
    d['to'] = r.obj()


def module_base(r, d):
    d['type'] = r.s()
    n = r.u16()
    d['plugs'] = [r.obj() for _ in range(n)]
    d['name'] = r.s()
    d['w'] = r.u16()
    d['rect'] = [r.i32() for _ in range(4)]


def h_ug(r, d):
    module_base(r, d)


HANDLERS = {
    'CPlug2': h_plug2, 'CPlugIO2': h_plugio, 'CPlugFeature': h_plugfeature, 'CLine2': h_line, 'CUG': h_ug,
}

def hexat(p, n=96):
    return o[p:p + n].hex()


def h_container(r, d):
    module_base(r, d)
    d['pm'] = r.obj()
    d['tail_at'] = r.p


def h_patchmgr(r, d):
    d['x0'] = r.u32()
    n = r.u32()
    d['names'] = {}
    for _ in range(n):
        k = r.u32(); d['names'][k] = r.s()
    d['params'] = []
    while True:
        t0 = r.u32()
        if t0 == 0xffffffff:
            break
        e = {'handle': r.u32()}
        e['plug'] = r.obj()
        e['name'] = r.s()
        e['b1'] = r.u8(); e['m1'] = r.i32(); e['b2'] = r.u8(); e['dtype'] = r.u32(); n = r.u32()
        t = e['dtype']
        if t == 6:
            e['vals'] = [r.f32() for _ in range(n)]
        elif t == 0:
            e['vals'] = [struct.unpack('<h', r.raw(2))[0] for _ in range(n)]
        elif t == 8:
            e['vals'] = [r.i32() for _ in range(n)]
        elif t == 1:
            e['vals'] = [r.s() for _ in range(n)]
        else:
            raise Stop('pm dtype %d at %x' % (t, r.p))
        d['params'].append(e)


def h_plugfeature3(r, d):
    h_plugfeature(r, d)
    d['extra'] = r.raw(1).hex()


R.depth_pm = 0
HANDLERS.update({'CContainer': h_container, 'CPatchManager': h_patchmgr, 'CPlugFeature4': h_plugfeature,
                 'CPlugFeature3': h_plugfeature3, 'CPlugFeature2': h_plugfeature})

def run(n=1, verbose=True):
    r = R()
    try:
        for _ in range(n):
            r.obj()
    except Stop as e:
        print('STOP:', e)
    except Exception as e:
        print('EXC:', repr(e))
    if verbose:
        print('pos %x next idx %x' % (r.p, r.next), hexat(r.p, 200))
    return r


def h_slider(r, d):
    module_base(r, d)
    d['handle'] = r.u32()
    n = r.u32()
    d['vals'] = [r.f64() for _ in range(n)]
    d['rect2'] = [r.i32() for _ in range(4)]
    d['s'] = r.s()


def h_combo(r, d):
    module_base(r, d)
    d['handle'] = r.u32()
    n = r.u32()
    for sz in (2, 4, 8, 1):
        if o[r.p + n * sz + 16:r.p + n * sz + 19] == b'\xff\xfe\xff':
            break
    else:
        raise Stop('combo values size? at %x' % r.p)
    fmt = {1: 'b', 2: 'h', 4: 'i', 8: 'd'}[sz]
    d['vals'] = list(struct.unpack_from('<%d%s' % (n, fmt), o, r.p)); r.p += n * sz
    d['rect2'] = [r.i32() for _ in range(4)]
    d['s'] = r.s()


for _c in ('control_ob_bitmap', 'CPlugin2', 'CPlugNameable', 'CSwitch', 'ui_param_enum_in2', 'ui_bitmap_frame',
           'control_ob_bitmap_tinted', 'ui_param_float_in2', 'control_ob_text', 'ui_text_to_float', 'ui_float_scaler',
           'ui_param_float_out2', 'ui_param_text_in', 'Ctl_PatchSel', 'ui_float_to_bool', 'ui_system_command'):
    HANDLERS[_c] = h_ug
HANDLERS['Ctl_Slider'] = h_slider
HANDLERS['Ctl_Combo'] = h_combo


def h_container(r, d):
    module_base(r, d)
    d['pm'] = r.obj()
    d['children'] = []
    while True:
        c = r.obj()
        if c is None:
            break
        d['children'].append(c)
    q = o.find(b'\xff\xfe\xff', r.p)
    d['ctail'] = r.raw(q - r.p).hex()
    if len(d['ctail']) != 136:
        print('  container %s tail len %d at %x: %s' % (d['name'], len(d['ctail']) // 2, r.p, d['ctail'][:200]))
    d['skin'] = r.s()
    d['cend'] = r.u8()


HANDLERS['CContainer'] = h_container


def h_gui(r, d):
    module_base(r, d)
    d['gui_tail'] = r.raw(22).hex()


def h_plugin(r, d):
    module_base(r, d)
    d['plugin_id'] = r.s()
    d['plugin_tail'] = r.raw(16).hex()


for _c in ('control_ob_bitmap', 'control_ob_bitmap_tinted', 'control_ob_text'):
    HANDLERS[_c] = h_gui
HANDLERS['CPlugin2'] = h_plugin


def h_plugnameable(r, d):
    plug_base(r, d)
    d['name'] = r.s()


HANDLERS['CPlugNameable'] = h_plugnameable
