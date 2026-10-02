"""A/B harness: play the same notes through the original MeowSynth.dll (under Wine, see setup.sh) and through
this port's engine (built as a dylib, driven with ctypes), and compare level, pitch and spectrum.
The t_*.py scripts next to this file are the comparisons the port was tuned with."""
import ctypes, os, struct, subprocess, sys, hashlib
import numpy as np
SP=os.path.dirname(os.path.abspath(__file__)); WINE=os.environ.get('MEOW_AB_WORK') or os.path.join(SP,'work')
ENGINE=os.path.join(SP,'..','..','src','meow_engine.c')
WRAP=os.path.join(os.environ.get('MPC_VST') or os.path.join(SP,'..','..','..','mpc-vst-plugins'),'wrapper')
SR=44100
def cmd(op,a=0,b=0,c=0.0): return struct.pack('<Iiif',op,a,b,c)
def orig(script, pre=40):
    """script: list of ('prog',n) ('set',idx,norm) ('midi',st,d1,d2) ('run',blocks) ('tempo',bpm) -> stereo float array"""
    out=b''; total=0
    for s in script:
        if s[0]=='prog': out+=cmd(1,s[1])+cmd(4,pre); total+=pre
        elif s[0]=='set': out+=cmd(2,s[1],0,s[2])
        elif s[0]=='midi': out+=cmd(3,s[1]|(s[2]<<8)|(s[3]<<16))
        elif s[0]=='run': out+=cmd(4,s[1]); total+=s[1]
        elif s[0]=='tempo': out+=cmd(6,0,0,s[1])
    key=hashlib.sha1(out).hexdigest()[:16]; cache=os.path.join(WINE,'cache_'+key+'.npy')
    if os.path.exists(cache): return np.load(cache)
    open(os.path.join(WINE,'cmd.bin'),'wb').write(out)
    env=dict(os.environ, WINEPREFIX=os.path.join(WINE,'prefix'), WINEDLLOVERRIDES='mscoree,mshtml=', WINEDEBUG='-all')
    subprocess.run([os.path.join(WINE,'wswine.bundle/bin/wine64'),'host.exe'],cwd=WINE,env=env,capture_output=True)   # ~2 s per run
    d=np.fromfile(os.path.join(WINE,'out.raw'),dtype=np.float32).reshape(-1,2,128)
    x=np.stack([d[:,0,:].reshape(-1),d[:,1,:].reshape(-1)],1)
    assert len(x)==total*128,(len(x),total*128)
    np.save(cache,x); return x
class ENG(ctypes.Structure):
    _fields_=[('create',ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_char_p)),('destroy',ctypes.CFUNCTYPE(None,ctypes.c_void_p)),
              ('midi',ctypes.CFUNCTYPE(None,ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int)),
              ('set_param',ctypes.CFUNCTYPE(None,ctypes.c_void_p,ctypes.c_char_p,ctypes.c_char_p)),
              ('get_param',ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int)),
              ('render',ctypes.CFUNCTYPE(None,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int16),ctypes.c_int)),('process',ctypes.c_void_p)]
_lib=None
def lib():
    global _lib
    so=os.path.join(WINE,'libmeow.dylib')
    subprocess.check_call(['clang','-O2','-shared','-I'+WRAP,ENGINE,'-lm','-o',so])
    _lib=ctypes.CDLL(so); _lib.mpc_engine.restype=ctypes.POINTER(ENG); return _lib.mpc_engine().contents
MAP={1:('chorus',lambda v:v*100),6:('env_e',lambda v:v*10),10:('env_m',lambda v:v*10),13:('env_o',lambda v:v*10),22:('env_w',lambda v:v*10),
     12:('noise',lambda v:v*100),17:('porta',lambda v:v*100),20:('vib_amt',lambda v:v*10),21:('vib_atk',lambda v:v*10),23:('vib_speed',lambda v:round(v*9)),
     25:('bend',lambda v:round(v*11)+1),26:('polycat',lambda v:round(v)),2:('cutoff',lambda v:v*10),18:('reso',lambda v:v*10),7:('envmod',lambda v:v*10),
     0:('fol_atk',lambda v:v*10),3:('fol_dec',lambda v:v*10),9:('gain',lambda v:v*10),5:('fmix',lambda v:v*100),8:('ftype',lambda v:round(v*4))}
def port(script, pre=40, trim=True):
    e=lib(); s=e.create(None); out=[]; buf=(ctypes.c_int16*256)()
    def run(n):
        for _ in range(n):
            e.render(s,buf,128); out.append(np.frombuffer(buf,dtype=np.int16).astype(np.float32).reshape(128,2)/32768.0)
    e.set_param(s,b'lfo_bpm',b'120')
    for c in script:
        if c[0]=='prog': e.set_param(s,b'preset',str(c[1]).encode()); run(pre)
        elif c[0]=='set':
            k,f=MAP[c[1]]; e.set_param(s,k.encode(),('%g'%f(c[2])).encode())
        elif c[0]=='midi': e.midi(s,bytes(c[1:4]),3)
        elif c[0]=='run': run(c[1])
        elif c[0]=='tempo': e.set_param(s,b'lfo_bpm',('%g'%c[1]).encode())
    e.destroy(s)
    x=np.concatenate(out)
    return x
def f0track(x,hop=512,win=2048,fmin=40,fmax=2000):
    out=[]
    for i in range(0,len(x)-win,hop):
        seg=x[i:i+win]
        if np.sqrt((seg**2).mean())<1e-4: out.append(0); continue
        seg=seg-seg.mean(); ac=np.correlate(seg,seg,'full')[win-1:]
        lo,hi=int(SR/fmax),int(SR/fmin); k=lo+int(np.argmax(ac[lo:hi]))
        if 0<k<len(ac)-1:
            d=(ac[k-1]-2*ac[k]+ac[k+1]); k=k+0.5*(ac[k-1]-ac[k+1])/d if d else k
        out.append(SR/k)
    return np.array(out)
def level(x,hop=512,win=2048):
    return np.array([20*np.log10(np.sqrt((x[i:i+win]**2).mean())+1e-7) for i in range(0,len(x)-win,hop)])
def centroid(x,hop=512,win=2048):
    f=np.fft.rfftfreq(win,1/SR); w=np.hanning(win); out=[]
    for i in range(0,len(x)-win,hop):
        S=np.abs(np.fft.rfft(x[i:i+win]*w)); out.append((S*f).sum()/S.sum() if S.sum()>1e-3 else 0)
    return np.array(out)
def on(n,v=100): return ('midi',0x90,n,v)
def off(n): return ('midi',0x80,n,0)
def secs(t): return ('run',int(round(t*SR/128)))
