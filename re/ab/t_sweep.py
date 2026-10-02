from ab import *
import numpy as np
print('single notes, Clear cat: level diff (port - original) and spectral centroid ratio')
for note in (36,48,60,66,72,84,96):
    for vel in (50,100,127):
        sc=[('prog',0),on(note,vel),secs(1.2),off(note),secs(.6)]
        a=orig(sc)[:,0]; b=port(sc)[:,0]
        la,lb=level(a),level(b); m=(la>-55)&(lb>-55); ca,cb=centroid(a),centroid(b)
        print('note %3d vel %3d: level mean %+.2f max %.2f dB | centroid ratio %.3f | peak %.3f/%.3f'%(note,vel,(lb-la)[m].mean(),np.abs(lb-la)[m].max(),np.median(cb[m]/ca[m]),np.abs(a).max(),np.abs(b).max()))
