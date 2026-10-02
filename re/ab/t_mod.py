from ab import *
import numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
def bend(v): v=int(8192+v*8191); return ('midi',0xe0,v&127,(v>>7)&127)
print('--- pitch bend: full up, semitones measured')
for p in (0,1,3):
    sc=[('prog',p),('set',20,0.0),on(60,100),secs(.5),bend(1.0),secs(.5),bend(-1.0),secs(.5),bend(0),secs(.3),off(60),secs(.3)]
    for lab,x in (('orig',orig(sc)[:,0]),('port',port(sc)[:,0])):
        f=f0track(x,hop=256,win=4096,fmin=60,fmax=1200); t=np.arange(len(f))*256/SR
        base=np.median(f[(t>0.3+0.116)&(t<0.5+0.116)]); up=np.median(f[(t>0.9+0.116)&(t<1.05+0.116)]); dn=np.median(f[(t>1.4+0.116)&(t<1.55+0.116)])
        print('preset %d %s: up %+.2f st, down %+.2f st'%(p,lab,12*np.log2(up/base),12*np.log2(dn/base)))
print('--- vibrato: Gospel cats (1/16) and Catband at 120 and 90 BPM, March cat (4 bar)')
fig,ax=plt.subplots(4,1,figsize=(13,11))
for r,(p,bpm,hold) in enumerate(((4,120,2.0),(4,90,2.0),(2,120,6.0),(1,120,6.0))):
    sc=[('tempo',bpm),('prog',p),on(60,100),secs(hold),off(60),secs(.5)]
    for lab,x,st in (('orig',orig(sc)[:,0],'-'),('port',port(sc)[:,0],'--')):
        f=f0track(x,hop=128,win=1024,fmin=100,fmax=1200); t=np.arange(len(f))*128/SR
        ax[r].plot(t,f,st,label=lab)
        m=(t>hold*0.5)&(t<hold*0.95)&(f>0)
        ff=f[m]; cents=1200*np.log2(ff/np.median(ff))
        sp=np.abs(np.fft.rfft((cents-cents.mean())*np.hanning(len(cents)))); fr=np.fft.rfftfreq(len(cents),128/SR)
        print('preset %d bpm %d %s: pitch swing +-%.0f cents (p2p/2), dominant rate %.2f Hz, median f0 %.1f'%(p,bpm,lab,(np.percentile(cents,99)-np.percentile(cents,1))/2,fr[np.argmax(sp[1:])+1],np.median(ff)))
    ax[r].set_title('preset %d at %d BPM: pitch Hz'%(p,bpm)); ax[r].legend(); ax[r].set_yscale('log')
plt.tight_layout(); plt.savefig(os.path.join(WINE,'t_mod.png'),dpi=55)
print('--- noise: Old cat (noise max) high-band level vs harmonic level, sustain')
for p in (0,1,3,4):
    sc=[('prog',p),('set',20,0.0),on(48,100),secs(1.5),off(48),secs(.3)]
    for lab,x in (('orig',orig(sc)[:,0]),('port',port(sc)[:,0])):
        seg=x[int(1.0*SR):int(1.5*SR)]; S=np.abs(np.fft.rfft(seg*np.hanning(len(seg))))**2; f=np.fft.rfftfreq(len(seg),1/SR)
        print('preset %d %s: total %.1f dB, 3-8 kHz band %.1f dB'%(p,lab,10*np.log10(S.sum()+1e-12),10*np.log10(S[(f>3000)&(f<8000)].sum()+1e-12)))
