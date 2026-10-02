from ab import *
import numpy as np
names=['Clear cat','Old cat','March cat','Catband','Gospel cats']
for p in range(5):
    sc=[('prog',p),on(60,100),secs(1.5),off(60),secs(1.0)]
    a=orig(sc)[:,0]; b=port(sc)[:,0]
    la,lb=level(a),level(b); m=(la>-60)&(lb>-60)
    ca,cb=centroid(a),centroid(b)
    print('%-12s peak orig %.3f port %.3f | level diff dB mean %+.2f max %.2f | centroid ratio median %.3f  | orig L=R %s'%(names[p],np.abs(a).max(),np.abs(b).max(),(lb-la)[m].mean(),np.abs(lb-la)[m].max(),np.median(cb[m]/ca[m]), np.allclose(orig(sc)[:,0],orig(sc)[:,1])))
