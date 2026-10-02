from ab import *
import numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
np.set_printoptions(suppress=True,linewidth=230,precision=0)
tests={
 'legato 60->72->(72 off)->60 off': [('prog',0),on(60),secs(.6),on(72),secs(.6),off(72),secs(.6),off(60),secs(.6)],
 'separate 60, gap, 72, gap, 48':   [('prog',0),on(60),secs(.4),off(60),secs(.5),on(72),secs(.4),off(72),secs(.5),on(48),secs(.4),off(48),secs(.5)],
 'retrigger in release 60 then 67': [('prog',0),on(60),secs(.3),off(60),secs(.05),on(67),secs(.5),off(67),secs(.5)],
 'first note ever (48)':            [('prog',0),on(48),secs(.5),off(48),secs(.3)],
}
fig,ax=plt.subplots(len(tests),2,figsize=(15,3.2*len(tests)))
for r,(name,sc) in enumerate(tests.items()):
    a=orig(sc)[:,0]; b=port(sc)[:,0]
    fa,fb=f0track(a),f0track(b); la,lb=level(a),level(b); t=np.arange(len(fa))*512/SR
    ax[r][0].plot(t,fa,label='original'); ax[r][0].plot(t,fb,'--',label='port'); ax[r][0].set_yscale('log'); ax[r][0].set_title(name+': pitch Hz'); ax[r][0].legend(); ax[r][0].grid(alpha=.3)
    ax[r][1].plot(t,la,label='original'); ax[r][1].plot(t,lb,'--',label='port'); ax[r][1].set_ylim(-70,0); ax[r][1].set_title('level dB'); ax[r][1].legend(); ax[r][1].grid(alpha=.3)
    m=(la>-50)&(lb>-50)&(fa>0)&(fb>0)
    cents=1200*np.log2(fb[m]/fa[m])
    print('%-34s level diff mean %+.2f max %.2f dB | pitch diff cents: median %+.1f, 95th pct %.0f, max %.0f | sounding frames orig %d port %d'%(name,(lb-la)[m].mean(),np.abs(lb-la)[m].max(),np.median(cents),np.percentile(np.abs(cents),95),np.abs(cents).max(),(la>-50).sum(),(lb>-50).sum()))
plt.tight_layout(); plt.savefig(os.path.join(WINE,'t_mono.png'),dpi=55)
