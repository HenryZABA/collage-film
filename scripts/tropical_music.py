#!/usr/bin/env python3
"""Original physical plucked-string and hand-percussion synthesis; no audio samples."""
def compose(duration, bpm, seed=51372):
    import numpy as np
    from scipy.signal import lfilter
    sr=48000;beat=60/bpm;N=round(duration*sr);mix=np.zeros((N,2));rng=np.random.default_rng(seed)
    def put(sound,time,gain,pan=0):
     start=int(time*sr);n=min(len(sound),N-start)
     if n<=0:return
     pan=np.clip(pan,-1,1);mix[start:start+n,0]+=sound[:n]*gain*np.sqrt((1-pan)/2);mix[start:start+n,1]+=sound[:n]*gain*np.sqrt((1+pan)/2)
    def note(midi):return 440*2**((midi-69)/12)
    def guitar(midi,seconds=2.2):
     f=note(midi);delay=int(sr/f-.5);size=int(sr*seconds);exc=rng.normal(0,.45,size=delay);exc-=exc.mean();exc=lfilter([.35,.65],[1],exc)
     drive=np.zeros(size);drive[:delay]=exc;den=np.zeros(delay+2);den[0]=1;den[-2:]=-.4985
     v=lfilter([1],den,drive);v=lfilter([.15,.7,.15],[1],v)
     # A quiet body resonance adds warmth to the string decay.
     t=np.arange(size)/sr;v+=.07*np.sin(2*np.pi*f*t)*np.exp(-t*3)
     v*=np.minimum(1,t/.002);return v
    chords=[[50,57,62,66,69],[47,54,57,62,66],[43,50,55,59,62],[45,52,57,59,64]]
    bars=int(np.ceil(duration/(4*beat)))
    for bar in range(bars):
     chord=chords[0 if bar==bars-1 else bar%4];base=bar*4*beat
     for pulse,vel in [(0,.58),(1.5,.35),(2,.46),(3.5,.34)]:
      for j,m in enumerate(chord):put(guitar(m),base+pulse*beat+j*.011,vel*.44,(j-2)*.12)
     # A simple changing upper melody, with offbeat answers.
     for off,m in [(1,chord[-1]),(2.5,chord[-2]),(3,chord[-1]+2)]:put(guitar(m,1.1),base+off*beat,.13,.2)
     t=np.arange(int(sr*.45))/sr
     for off in [0,2]:
      freq=note(chord[0]-12);put(np.sin(2*np.pi*freq*t)*np.exp(-t*6),base+off*beat,.24)
    for i in range(int(np.ceil(duration/beat))):
     t=np.arange(int(sr*.18))/sr
     # Low hand drum, alternating open/slap conga, and dry woodblock.
     if i%2==0:put(np.sin(2*np.pi*(78*t+4*(1-np.exp(-t*24))))*np.exp(-t*24),i*beat,.19)
     f=210 if i%2 else 150;conga=(np.sin(2*np.pi*f*t)+.3*np.sin(2*np.pi*f*1.52*t))*np.exp(-t*26);put(conga,i*beat+.5*beat,.095,(-1)**i*.3)
     t2=np.arange(int(sr*.045))/sr;clave=(np.sin(2*np.pi*1700*t2)+.6*np.sin(2*np.pi*2400*t2))*np.exp(-t2*150)
     if i%4 in [1,3]:put(clave,i*beat+.75*beat,.032,-.35)
     for half in [0,.5]:
      tn=np.arange(int(sr*.055))/sr;noise=rng.normal(0,1,len(tn));shaker=lfilter([1,-.94],[1],noise)*np.exp(-tn*70)*np.minimum(1,tn/.003);put(shaker,i*beat+half*beat,.023,.38)
    # Short stereo room reflections, retained as part of this original arrangement.
    dry=mix.copy()
    for delay,gain in [(.055,.09),(.11,.065),(.19,.035)]:
     n=int(delay*sr);mix[n:]+=dry[:-n,::-1]*gain
    mix=np.tanh(mix*1.45);mix*=.87/max(np.max(np.abs(mix)),.87)
    fade=int(.035*sr);mix[:fade]*=np.linspace(0,1,fade)[:,None];fade=int(.5*sr);mix[-fade:]*=np.linspace(1,0,fade)[:,None]
    return sr,mix
