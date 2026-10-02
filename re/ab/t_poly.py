from ab import *
import numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
def spec(ax,x,title):
    ax.specgram(x+1e-9,NFFT=4096,Fs=SR,noverlap=3584,cmap='magma',vmin=-130,vmax=-30); ax.set_ylim(0,1500); ax.set_title(title,fontsize=9)
tests={
 'poly (Catband): 48, then 60 overlapping, then 67': [('prog',3),on(48),secs(.5),on(60),secs(.5),on(67),secs(.5),off(48),off(60),off(67),secs(.8)],
 'poly: separate notes 60 gap 72':                   [('prog',3),on(60),secs(.4),off(60),secs(.5),on(72),secs(.4),off(72),secs(.6)],
 'poly: same note twice while held (60,60)':         [('prog',3),on(60),secs(.5),on(60),secs(.5),off(60),secs(.6)],
 'poly: 10-note cluster':                            [('prog',3)]+[on(48+2*k) for k in range(10)]+[secs(1.0)]+[off(48+2*k) for k in range(10)]+[secs(.6)],
}
fig,ax=plt.subplots(len(tests),2,figsize=(15,3.2*len(tests)))
for r,(name,sc) in enumerate(tests.items()):
    a=orig(sc)[:,0]; b=port(sc)[:,0]
    spec(ax[r][0],a,'ORIGINAL '+name); spec(ax[r][1],b,'port')
    la,lb=level(a),level(b); m=(la>-50)&(lb>-50)
    print('%-52s peak orig %.3f port %.3f | level diff mean %+.2f max %.2f dB'%(name,np.abs(a).max(),np.abs(b).max(),(lb-la)[m].mean(),np.abs(lb-la)[m].max()))
    if 'cluster' in name:
        seg=a[int(.6*SR)+5120:int(.6*SR)+5120+32768]; segb=b[int(.6*SR)+5120:int(.6*SR)+5120+32768]
        f=np.fft.rfftfreq(32768,1/SR); w=np.hanning(32768)
        for lab,sg in (('orig',seg),('port',segb)):
            S=np.abs(np.fft.rfft(sg*w)); out=[]
            for k in range(10):
                f0=440*2**((48+2*k-69)/12); i=np.argmin(abs(f-f0)); out.append(20*np.log10(S[i-3:i+4].max()+1e-9))
            print('   fundamentals dB',lab,np.round(out,0))
plt.tight_layout(); plt.savefig(os.path.join(WINE,'t_poly.png'),dpi=55)
