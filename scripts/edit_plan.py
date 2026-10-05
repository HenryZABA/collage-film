#!/usr/bin/env python3
# coding: utf-8
"""Apply an Agent-authored editing script; measure framing, never invent a story."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from PIL import Image

RATIOS = {'9:16': (1080,1920), '3:4': (1080,1440), '4:5': (1080,1350), '1:1': (1080,1080), '16:9': (1920,1080)}

def num(value, low, high, name):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be finite in {low}..{high}')
    return float(value)

def text(value, name):
    if not isinstance(value,str) or not value.strip() or len(value)>800:
        raise ValueError(f'{name} requires a short non-empty description')
    return value

def apply_plan(job, script, base):
    if job.get('style')!='cutout-reveal': raise ValueError('Editing scripts require cutout-reveal')
    if not isinstance(script,dict) or set(script)-{'schema_version','story','bpm','shots','coverage'} or script.get('schema_version')!=1:
        raise ValueError('Script requires schema_version=1, story, bpm and shots')
    coverage=script.get('coverage','all')
    if coverage not in ('all','selected'): raise ValueError('coverage must be all or selected')
    story=text(script.get('story'),'story'); bpm=num(script.get('bpm'),40,240,'bpm')
    shots=script.get('shots')
    if not isinstance(shots,list) or not 2<=len(shots)<=60: raise ValueError('Script needs 2..60 shots')
    width,height=RATIOS[job['ratio']]
    resolution=job.get('resolution','1080p')
    if resolution not in ('1080p','4k'): raise ValueError('resolution must be 1080p or 4k')
    if resolution=='4k':
        factor=3840/max(width,height);width,height=round(width*factor/2)*2,round(height*factor/2)*2
    seen=set(); scenes=[]; measures=[]; warnings=[]; time=0
    for k,shot in enumerate(shots,1):
        if not isinstance(shot,dict) or set(shot)-{'source_index','source_sha256','role','connection','beats','lead_in','zoom','anchor','quality_note'}:
            raise ValueError(f'Unknown shot fields at {k}')
        index=shot.get('source_index')
        if type(index) is not int or not 1<=index<=len(job['scenes']) or index in seen: raise ValueError('Source indices must be unique and in range')
        seen.add(index); scene=copy.deepcopy(job['scenes'][index-1])
        role=text(shot.get('role'),'role'); connection=text(shot.get('connection'),'connection'); note=text(shot.get('quality_note'),'quality_note')
        source=(base/scene['photo']).resolve(); digest=hashlib.sha256(source.read_bytes()).hexdigest()
        if shot.get('source_sha256')!=digest: raise ValueError(f'Shot {k} source_sha256 does not match the viewed normalized photo')
        beats=num(shot.get('beats'),.25,32,'beats'); duration=round(60/bpm*beats,6)
        if not .4<=duration<=30: raise ValueError('Shot durations must be .4..30 seconds')
        lead=num(shot.get('lead_in',.2),0,1,'lead_in') if k>1 else 0
        if k>1: lead=min(lead,scenes[-1]['duration']/2)
        zoom=num(shot.get('zoom',1),1,3,'zoom'); anchor=shot.get('anchor')
        if anchor is not None and (not isinstance(anchor,dict) or set(anchor)!={'x','y'}): raise ValueError('anchor must contain x and y frame fractions')
        with Image.open(source) as im: sw,sh=im.size
        fit=scene.get('fit','cover'); scale=max(width/sw,height/sh) if fit=='cover' else min(width/sw,height/sh)
        px=num(scene.get('position',{}).get('x',.5),0,1,'position.x'); py=num(scene.get('position',{}).get('y',.5),0,1,'position.y')
        ox=(width-sw*scale)*px; oy=(height-sh*scale)*py
        bbox=None; fx=fy=0
        if scene.get('cutout'):
            with Image.open(base/scene['cutout']) as im:
                if im.size!=(sw,sh): raise ValueError('Cutout and photo dimensions must match')
                bbox=im.convert('RGBA').getchannel('A').point(lambda a:255 if a>24 else 0).getbbox()
            if bbox is None: raise ValueError('Cutout has no foreground')
        if anchor:
            if bbox is None: raise ValueError('Subject anchor requires a cutout')
            ax=num(anchor['x'],0,1,'anchor.x'); ay=num(anchor['y'],0,1,'anchor.y')
            cx=((bbox[0]+bbox[2])/2*scale+ox-width/2)*zoom+width/2
            cy=((bbox[1]+bbox[3])/2*scale+oy-height/2)*zoom+height/2
            fx=(ax*width-cx)/width; fy=(ay*height-cy)/height
            if fit=='cover':
                limit=(zoom-1)/2
                wanted=(fx,fy); fx=max(-limit,min(limit,fx)); fy=max(-limit,min(limit,fy))
                if max(abs(fx-wanted[0]),abs(fy-wanted[1]))>.00001:
                    warnings.append({'shot':k,'code':'anchor_limited_by_full_frame_coverage','note':'Requested position was limited to avoid empty photo edges; choose a different crop/photo if unsuitable'})
        framing={'zoom':zoom,'x':round(fx,6),'y':round(fy,6)}
        scene.update(duration=duration,leadIn=round(lead,6),framing=framing); scenes.append(scene)
        measure={'shot':k,'source_index':index,'source_sha256':digest,'role':role,'connection':connection,'quality_note':note,'start':round(time,6),'duration':duration,'beats':beats,'lead_in':scene['leadIn'],'framing':framing,'pixel_scale':round(scale*zoom,4),'subject_height_fraction':None,'subject_bounds':None}
        if bbox:
            bounds=[((bbox[0]*scale+ox-width/2)*zoom+width/2)/width+fx,((bbox[1]*scale+oy-height/2)*zoom+height/2)/height+fy,((bbox[2]*scale+ox-width/2)*zoom+width/2)/width+fx,((bbox[3]*scale+oy-height/2)*zoom+height/2)/height+fy]
            measure.update(subject_bounds=[round(v,4) for v in bounds],subject_height_fraction=round((bbox[3]-bbox[1])*scale*zoom/height,4))
            if min(bounds[:2])<-.005 or max(bounds[2:])>1.005:
                warnings.append({'shot':k,'code':'subject_cropped','note':'Selected subject leaves frame; inspect crop and revise framing'})
        if scale*zoom>1.25: warnings.append({'shot':k,'code':'pixel_upscale','value':round(scale*zoom,3),'note':'More than 1.25 output pixels per source pixel; visual sharpness review required, not a quality guarantee'})
        if measure['subject_height_fraction'] and measure['subject_height_fraction']<.18:
            warnings.append({'shot':k,'code':'small_subject','note':'Subject under 18% of frame height; decide whether it is an intentional wide shot'})
        measures.append(measure); time+=duration
    for k in range(2,len(measures)):
        if all(m['subject_height_fraction'] is not None and m['subject_height_fraction']<.18 for m in measures[k-2:k+1]):
            warnings.append({'shot':k+1,'code':'three_small_subjects_in_a_row','note':'Review sequence: alternate shot sizes, revise framing or keep this run only when the story warrants it'})
    if time+job.get('endCard',{}).get('duration',0)>300: raise ValueError('Video exceeds 300 seconds')
    omitted=sorted(set(range(1,len(job['scenes'])+1))-seen)
    if coverage=='all' and omitted: raise ValueError(f'Full coverage omitted source indices: {omitted}; selected requires user-authorized curation')
    result=copy.deepcopy(job); result['scenes']=scenes
    report={'schema_version':1,'coverage':coverage,'input_count':len(job['scenes']),'used_count':len(shots),'width':width,'height':height,'story':story,'bpm':bpm,'duration':round(time,6),'shots':measures,'omitted_source_indices':sorted(set(range(1,len(job['scenes'])+1))-seen),'warnings':warnings,'visual_review_required':True,'beat_detection':False,'sharpness_estimated':False}
    return result,report

def markdown(report):
    lines=['# 剪辑脚本','',report['story'],'',f"{report['bpm']:g} BPM · {report['duration']:g} 秒 · 音乐使用已知节拍，不自动识别拍点。",'','| 镜头 | 来源序号 | 时间 | 叙事作用 / 衔接 | 主体高度 | 放大像素倍率 |','| --- | --- | --- | --- | --- | --- |']
    for s in report['shots']:
        size='—' if s['subject_height_fraction'] is None else f"{s['subject_height_fraction']*100:.0f}%"
        desc=(s['role']+'；'+s['connection']).replace('|','/').replace('\n',' ')
        lines.append(f"| {s['shot']} | {s['source_index']} | {s['start']:g}–{s['start']+s['duration']:g}s | {desc} | {size} | {s['pixel_scale']:g}× |")
    lines += ['','## 画质与构图判断','']+[f"- 镜头 {s['shot']}：{s['quality_note']}" for s in report['shots']]
    lines += ['','## 需要复查','']+[f"- 镜头 {w['shot']}：{w['code']} — {w['note']}" for w in report['warnings']]
    return '\n'.join(lines)+'\n'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--job',type=Path,required=True);p.add_argument('--script',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():p.error('Output exists; choose a fresh job filename')
    try:
        job,report=apply_plan(json.loads(a.job.read_text()),json.loads(a.script.read_text()),a.job.resolve().parent)
        a.out.parent.mkdir(parents=True,exist_ok=True)
        # Keep assets relative to the new config directory, including a relocated revision.
        import os
        for scene in job['scenes']:
            for key in ['photo','cutout']:
                if key in scene:scene[key]=os.path.relpath((a.job.resolve().parent/scene[key]).resolve(),a.out.resolve().parent)
        for key in ['bgm']:
            if job.get(key):job[key]['path']=os.path.relpath((a.job.resolve().parent/job[key]['path']).resolve(),a.out.resolve().parent)
        if job.get('font'):job['font']=os.path.relpath((a.job.resolve().parent/job['font']).resolve(),a.out.resolve().parent)
        a.out.write_text(json.dumps(job,ensure_ascii=False,indent=2)+'\n');a.out.with_suffix('.edit-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');a.out.with_suffix('.edit-script.md').write_text(markdown(report))
        print(json.dumps({'ok':True,'job':str(a.out),'duration':report['duration'],'warnings':report['warnings'],'visual_review_required':True},ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError,TypeError) as exc:p.error(str(exc))
if __name__=='__main__':main()
