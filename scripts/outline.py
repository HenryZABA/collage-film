#!/usr/bin/env python3
"""Create an adaptive SVG contour overlay; never modify source PNG pixels."""
import argparse,json,math
from pathlib import Path

def create_outline(source, output, width, height, fit='cover', zoom=1, radius_ratio=.012, max_radius=12, per_component=False):
    import cv2
    import numpy as np
    from PIL import Image
    with Image.open(source) as im:
        if 'A' not in im.getbands():raise ValueError('Input requires alpha')
        sw,sh=im.size;alpha=np.array(im.getchannel('A'));bbox=im.getchannel('A').point(lambda a:255 if a>24 else 0).getbbox()
    if not bbox or alpha.min()==255:raise ValueError('Input requires visible and transparent pixels')
    values=[width,height,zoom,radius_ratio,max_radius]
    if not all(math.isfinite(v) and v>0 for v in values) or fit not in ('cover','contain'):raise ValueError('Invalid display geometry or outline settings')
    scale=(max if fit=='cover' else min)(width/sw,height/sh)*zoom
    default=min(max_radius,min(bbox[2]-bbox[0],bbox[3]-bbox[1])*scale*radius_ratio)
    contours,hierarchy=cv2.findContours((alpha>=128).astype('uint8')*255,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    paths=[];radii={}
    if hierarchy is not None:
        for n,c in enumerate(contours):
            if hierarchy[0,n,3]!=-1:continue
            _,_,w,h=cv2.boundingRect(c)
            radii[n]=min(max_radius,min(w,h)*scale*radius_ratio) if per_component else default
        for n,c in enumerate(contours):
            parent=int(hierarchy[0,n,3]);root=parent if parent!=-1 else n
            if root not in radii or cv2.contourArea(c)*scale**2<3:continue
            points=cv2.approxPolyDP(c,.45/scale,True).reshape(-1,2)
            if len(points)<3:continue
            d='M'+' L'.join(f'{x},{y}' for x,y in points)+' Z'
            paths.append(f'<path d="{d}" stroke-width="{2*radii[root]/scale:.6f}"/>')
    if not paths:raise ValueError('No usable alpha contours at threshold 128; inspect mask')
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{sw}" height="{sh}" viewBox="0 0 {sw} {sh}"><g fill="none" stroke="#ffffff" stroke-linejoin="round" stroke-linecap="round">'+''.join(paths)+'</g></svg>'
    with Path(output).open('x') as f:f.write(svg)
    return {'radius_px':default,'component_radii_px':list(radii.values()),'per_component':per_component,'paths':len(paths),'display_scale':scale,'source_pixels_modified':False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--width',type=int,required=True);p.add_argument('--height',type=int,required=True)
    p.add_argument('--fit',choices=['cover','contain'],default='cover');p.add_argument('--zoom',type=float,default=1)
    p.add_argument('--radius-ratio',type=float,default=.012);p.add_argument('--max-radius',type=float,default=12)
    p.add_argument('--per-component',action='store_true');a=p.parse_args()
    try:print(json.dumps(create_outline(a.input,a.output,a.width,a.height,a.fit,a.zoom,a.radius_ratio,a.max_radius,a.per_component)))
    except (ValueError,OSError,ImportError) as e:p.error(f'{e}. Optional dependency: opencv-python-headless in the active Python environment')
if __name__=='__main__':main()
