import struct, re, subprocess, sys
import os
DLL=os.environ.get('MEOW_DLL') or os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','MeowSynth.dll')   # disassembly helper (macOS/LLVM objdump)
class Img:
    def __init__(self, path):
        self.path=path; self.d=open(path,'rb').read(); d=self.d
        pe=struct.unpack_from('<I',d,0x3c)[0]
        self.base=struct.unpack_from('<I',d,pe+52)[0]
        nsec=struct.unpack_from('<H',d,pe+6)[0]; opt=struct.unpack_from('<H',d,pe+20)[0]
        self.secs=[]
        for i in range(nsec):
            o=pe+24+opt+i*40
            vs,va,rs,rp=struct.unpack_from('<IIII',d,o+8); self.secs.append((d[o:o+8].rstrip(b'\0').decode(),va,vs,rp,rs))
    def off(self,va):
        rva=va-self.base
        for n,a,vs,rp,rs in self.secs:
            if a<=rva<a+max(vs,rs): return rva-a+rp
        raise ValueError(hex(va))
    def va(self,off):
        for n,a,vs,rp,rs in self.secs:
            if rp<=off<rp+rs: return off-rp+a+self.base
        raise ValueError(hex(off))
    def xrefs(self,va):
        pat=struct.pack('<I',va)
        return [self.va(m.start()) for m in re.finditer(re.escape(pat),self.d)]
    def u32(self,va): return struct.unpack_from('<I',self.d,self.off(va))[0]
    def f32(self,va): return struct.unpack_from('<f',self.d,self.off(va))[0]
    def f64(self,va): return struct.unpack_from('<d',self.d,self.off(va))[0]
    def cstr(self,va):
        o=self.off(va); e=self.d.index(b'\0',o); return self.d[o:e].decode('latin1')
    def find(self,s):
        return [self.va(m.start()) for m in re.finditer(re.escape(s),self.d)]
    def dis(self,start,n=200,stop_ret=True):
        out=subprocess.run(['objdump','-d','--x86-asm-syntax=intel','--no-show-raw-insn','--start-address=%#x'%start,'--stop-address=%#x'%(start+n),self.path],capture_output=True,text=True).stdout
        lines=[l for l in out.split('\n') if re.match(r'^\s*[0-9a-f]+:',l)]
        res=[]
        for l in lines:
            l=re.sub(r'\s*<[^>]*>','',l)
            # annotate constants
            m=re.search(r'(?:dword|qword|tbyte) ptr \[(0x1[0-9a-f]{7})\]',l)
            if m:
                a=int(m.group(1),16)
                try:
                    if 'qword' in l: l+='   ; f64=%g'%self.f64(a)
                    elif 'dword' in l and re.search(r'\bf[a-z]+\b',l.split('\t')[1] if '\t' in l else l): l+='   ; f32=%g'%self.f32(a)
                    else: l+='   ; u32=%#x'%self.u32(a)
                except Exception: pass
            res.append(l.strip())
            if stop_ret and re.search(r'\bret\b',l) : break
        return '\n'.join(res)
    def vtable(self,rtti_name):
        td=self.find(rtti_name.encode())[0]-8
        cols=[x for x in self.xrefs(td)]
        vts=[]
        for c in cols:
            col=c-12
            for x in self.xrefs(col):
                vts.append(x+4)
        return vts
    def vfuncs(self,vt,n=40):
        out=[]
        for i in range(n):
            try: f=self.u32(vt+4*i)
            except Exception: break
            if not (self.base+0x1000<=f<self.base+0x13e000): break
            out.append(f)
        return out
main=Img(DLL)
