#!/usr/bin/env python3
"""Create an original deterministic preview music bed; no sampled or borrowed audio."""
import argparse, math, wave
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True)
    p.add_argument('--duration',type=float,default=12)
    p.add_argument('--bpm',type=float,default=110)
    a=p.parse_args()
    if not 1<=a.duration<=300 or not 40<=a.bpm<=240:p.error('duration 1..300 seconds, BPM 40..240')
    try: import numpy as np
    except ImportError:p.error('Install numpy in your environment: python3 -m pip install numpy')
    dst=Path(a.output).expanduser()
    if dst.exists():p.error('Output exists; choose a new filename')
    sr=44100;n=round(sr*a.duration);mix=np.zeros((n,2),dtype=np.float64);beat=60/a.bpm
    rng=np.random.default_rng(1806)
    def add(signal,start,pan=0):
        i=round(start*sr)
        if i>=n:return
        signal=signal[:n-i]
        mix[i:i+len(signal),0]+=signal*math.sqrt((1-pan)/2)
        mix[i:i+len(signal),1]+=signal*math.sqrt((1+pan)/2)
    chords=[[57,60,64,67],[53,57,60,64],[48,52,55,59],[55,59,62,65]]
    for b in range(math.ceil(a.duration/beat)):
        time=b*beat;chord=chords[(b//4)%4]
        t=np.arange(round(sr*beat*.85))/sr
        freq=440*2**((chord[0]-12-69)/12)
        add(.24*np.sin(2*np.pi*freq*t)*(1-np.exp(-t*90))*np.exp(-t*5),time)
        t=np.arange(round(sr*.19))/sr
        add(.35*np.sin(2*np.pi*(48*t+45*.04*(1-np.exp(-t/.04))))*np.exp(-t*24),time)
        for half in [0,.5]:
            t=np.arange(round(sr*.07))/sr;noise=rng.standard_normal(len(t));noise=np.diff(noise,prepend=0)
            add(.025*noise*np.exp(-t*75),time+beat*half,.25)
        if b%2:
            t=np.arange(round(sr*.14))/sr
            add(.07*rng.standard_normal(len(t))*np.exp(-t*29),time,-.15)
        for k,midi in enumerate(chord):
            t=np.arange(round(sr*beat*1.6))/sr;f=440*2**((midi+12-69)/12)
            tone=(np.sin(2*np.pi*f*t)+.22*np.sin(2*np.pi*2*f*t))*np.exp(-t*3)*(1-np.exp(-t*80))
            add(.065*tone,time+k*beat/4,[-.4,.2,-.2,.4][k])
    t=np.arange(n)/sr;fade=np.minimum(1,t/.12)*np.minimum(1,np.maximum(0,(a.duration-t)/.7))
    mix*=fade[:,None];peak=np.max(np.abs(mix));mix*=.82/max(peak,.01)
    dst.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(dst),'wb') as w:
        w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr);w.writeframes((mix*32767).astype('<i2').tobytes())
    print(str(dst))
if __name__=='__main__':main()
