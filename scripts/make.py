#!/usr/bin/env python3
"""Prepare photographs, segment subjects and build an editable HyperFrames reel."""
from __future__ import annotations
import argparse, hashlib, json, math, platform, shutil, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PLATFORMS=['instagram','tiktok','douyin','xiaohongshu','youtube','custom']
RATIOS=['9:16','3:4','4:5','1:1','16:9']

def call(args, cwd=None):
    subprocess.run([str(a) for a in args],cwd=cwd,check=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--doctor',action='store_true')
    p.add_argument('--images',nargs='+',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--platform',choices=PLATFORMS)
    p.add_argument('--ratio',choices=RATIOS)
    p.add_argument('--title',default='Small moments')
    p.add_argument('--text',default=None,help='Small persistent centered caption; omit for clean photography')
    p.add_argument('--end-title',default='',help='Optional black end card')
    p.add_argument('--grade',choices=['none','warm-film','cool-editorial'])
    p.add_argument('--fit',choices=['auto','cover','contain'],default='auto',help='auto retains complete detected subjects; cover allows deliberate crop')
    p.add_argument('--pace',choices=['reference','breathing'],help='Default preset: reference. reference = 1 beat per photo; breathing = alternating 1 and 2 beats. Explicit seconds/beats-per-photo overrides this pattern')
    uniform=p.add_mutually_exclusive_group()
    uniform.add_argument('--seconds-per-photo',type=float,help='Uniform photo duration in seconds (.4..30); overrides --pace. Cannot combine with --beats-per-photo')
    p.add_argument('--bpm',type=float,help='Known constant musical tempo; not automatic beat detection')
    uniform.add_argument('--beats-per-photo',type=float,help='Uniform beats per photo (.25..32), converted using --bpm/preset BPM; overrides --pace. Cannot combine with --seconds-per-photo')
    p.add_argument('--lead-in',type=float,help='Cutout lead-in in seconds (0..1); default preset .2, about 6 frames at 30 fps. Capped at half the preceding photo duration')
    p.add_argument('--skip-cutout',default='',help='Comma-separated 1-based image indices for intentional full-photo cuts')
    p.add_argument('--backend',choices=['auto','birefnet','sam2','vision','rembg'],default='auto')
    p.add_argument('--edit-script',type=Path,help='Agent-authored story/order/beat/zoom/anchor plan; see references/editing-script.md')
    p.add_argument('--subjects',type=Path,help='Agent-reviewed per-photo subject plan; schema_version=1, images with index, subject, backend and optional SAM 2 objects')
    p.add_argument('--refine',choices=['auto','none','vitmatte'],default='auto',help='SAM 2 edges: auto uses installed ViTMatte; per-image plan can override this')
    m=p.add_mutually_exclusive_group()
    m.add_argument('--music',type=Path)
    m.add_argument('--demo-music',action='store_true',help='Create a simple original preview music bed')
    m.add_argument('--silent',action='store_true')
    p.add_argument('--check',action='store_true')
    p.add_argument('--render',action='store_true',help='Check then render MP4; only pass when user requested a finished video')
    a=p.parse_args()
    if a.doctor:
        modules={}
        for mod in ['PIL','numpy']:
            try:__import__(mod);modules[mod]=True
            except ImportError:modules[mod]=False
        backends={}
        if all(modules.values()):
            from cutout import backend_status
            backends={name:backend_status(name) for name in ['birefnet','sam2','vitmatte']}
        print(json.dumps({'python':sys.version.split()[0],'os':platform.system(),'modules':modules,'executables':{x:bool(shutil.which(x)) for x in ['node','npx','ffmpeg','ffprobe','swift']},'segmentation_backends':backends,'native_segmentation':'macOS 14+ Vision fallback; quality backends require explicit one-time setup','paid_api_required':False},indent=2))
        return 0
    if not a.images or not a.output or not a.platform or not a.ratio:p.error('--images, --output, --platform and --ratio are required')
    if not (a.music or a.demo_music or a.silent):p.error('Choose --music FILE, --demo-music or --silent after collecting music preference')
    if not 2<=len(a.images)<=60:p.error('Use 2..60 photos for a montage')
    if a.output.expanduser().exists():p.error('Output exists; choose a fresh project directory')
    if not all(x.expanduser().is_file() for x in a.images):p.error('Every image path must exist')
    if a.music and not a.music.expanduser().is_file():p.error('Music file does not exist')
    if a.edit_script and not a.edit_script.expanduser().is_file():p.error('Editing script does not exist')
    if a.edit_script and (a.seconds_per_photo is not None or a.beats_per_photo is not None or a.pace is not None):p.error('--edit-script owns order and durations; do not combine with uniform timing or --pace')
    try:
        skip={int(x.strip()) for x in a.skip_cutout.split(',') if x.strip()}
    except ValueError:p.error('--skip-cutout expects comma-separated integers')
    if any(i<1 or i>len(a.images) for i in skip):p.error('skip-cutout index out of range')
    subject_plans={}
    if a.subjects:
        try:
            from cutout import validate_selection
            plan=json.loads(a.subjects.expanduser().read_text())
            if not isinstance(plan,dict) or set(plan)-{'schema_version','images'} or plan.get('schema_version')!=1 or not isinstance(plan.get('images'),list):raise ValueError('Subject plan requires schema_version=1 and images array')
            for item in plan['images']:
                if not isinstance(item,dict) or set(item)-{'index','subject','backend','source_sha256','objects','instances','refine'}:raise ValueError('Unknown subject-plan field')
                i=item.get('index')
                if type(i) is not int or not 1<=i<=len(a.images) or i in subject_plans or i in skip:raise ValueError('Subject indices must be unique, in range and not skipped')
                if not isinstance(item.get('subject'),str) or not item['subject'].strip():raise ValueError('Each plan needs a subject description based on the actual image')
                backend=item.get('backend',a.backend)
                if backend not in ['auto','birefnet','sam2','vision','rembg']:raise ValueError('Unsupported subject backend')
                digest=hashlib.sha256(a.images[i-1].expanduser().read_bytes()).hexdigest()
                if item.get('source_sha256',digest)!=digest:raise ValueError(f'Subject plan for image {i} does not match the input hash')
                if backend=='sam2':
                    if item.get('source_sha256')!=digest:raise ValueError('SAM 2 plans require source_sha256 to bind geometry to the viewed original')
                    validate_selection({'subject':item['subject'],'objects':item.get('objects')})
                elif 'objects' in item:raise ValueError('Only SAM 2 consumes object boxes/points')
                if 'instances' in item and backend!='vision':raise ValueError('Instance IDs are specific to Vision')
                if item.get('refine',a.refine) not in ['auto','none','vitmatte']:raise ValueError('Unknown edge refinement mode')
                if item.get('refine',a.refine)=='vitmatte' and backend!='sam2':raise ValueError('Explicit ViTMatte refinement requires SAM 2')
                subject_plans[i]={**item,'backend':backend,'source_sha256':digest,'refine':item.get('refine',a.refine)}
        except (ValueError,OSError) as exc:p.error(str(exc))
    if a.backend=='sam2' and any(i not in skip and i not in subject_plans for i in range(1,len(a.images)+1)):
        p.error('--backend sam2 needs a --subjects plan for every unskipped photograph')
    if a.refine=='vitmatte' and a.backend!='sam2' and any(i not in skip and i not in subject_plans for i in range(1,len(a.images)+1)):
        p.error('Explicit ViTMatte refinement requires SAM 2 for every unplanned photograph; use per-image refine overrides in --subjects for mixed backends')
    preset=json.loads((ROOT/'assets/preset.json').read_text())
    script=json.loads(a.edit_script.expanduser().read_text()) if a.edit_script else None
    if script is not None and not isinstance(script,dict):p.error('Editing script must be an object')
    bpm=script.get('bpm') if script is not None else a.bpm if a.bpm is not None else preset.get('bpm',100)
    if script is not None and a.bpm is not None and a.bpm!=bpm:p.error('--bpm conflicts with the editing script BPM')
    pace=a.pace if a.pace is not None else preset.get('pace','reference')
    lead=a.lead_in if a.lead_in is not None else preset.get('transitionSeconds',.2)
    def finite_number(value):
        return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
    if not finite_number(bpm) or not 40<=bpm<=240:p.error('BPM must be a finite number in 40..240')
    if pace not in ['reference','breathing']:p.error('Preset pace must be reference or breathing')
    if not finite_number(lead) or not 0<=lead<=1:p.error('lead-in must be a finite number in 0..1 seconds')
    if a.edit_script:
        # The script owns timing; placeholder source shots are only used during segmentation.
        photo_durations=[.6]*len(a.images);timing_mode='edit-script-pending'
    elif a.seconds_per_photo is not None:
        if not finite_number(a.seconds_per_photo) or not .4<=a.seconds_per_photo<=30:p.error('seconds-per-photo must be .4..30')
        photo_durations=[a.seconds_per_photo]*len(a.images);timing_mode='uniform-seconds'
    elif a.beats_per_photo is not None:
        if not finite_number(a.beats_per_photo) or not .25<=a.beats_per_photo<=32:p.error('beats-per-photo must be .25..32')
        photo_durations=[60/bpm*a.beats_per_photo]*len(a.images);timing_mode='uniform-beats'
    else:
        photo_durations=[60/bpm*(2 if pace=='breathing' and i%2 else 1) for i in range(len(a.images))];timing_mode='pace'
    if any(not .4<=seconds<=30 for seconds in photo_durations):p.error('This tempo/pattern produces a photo duration outside the renderer range .4..30 seconds; choose a supported --beats-per-photo or --seconds-per-photo')
    photo_durations=[round(seconds,6) for seconds in photo_durations]
    lead_ins=[0]+[round(min(lead,seconds/2),6) for seconds in photo_durations[:-1]]
    duration=round(sum(photo_durations)+(2 if a.end_title else 0),6)
    if duration>300:p.error('Total duration must be <=300 seconds')
    for x in ['node','ffmpeg','ffprobe']:
        if not shutil.which(x):p.error(f'Missing executable: {x}')
    try:from PIL import Image,ImageOps
    except ImportError:p.error('Install Pillow in this Python environment')
    out=a.output.expanduser().resolve();out.mkdir(parents=True)
    inputs=out/'inputs';inputs.mkdir();cutouts=out/'cutouts';cutouts.mkdir()
    sources=[];normalized=[];warnings=[]
    for i,src in enumerate(a.images,1):
        src=src.expanduser().resolve()
        # Decode/EXIF-normalize both the photo and segmentation source identically.
        with Image.open(src) as im:
            if im.width*im.height>32_000_000:raise ValueError('Input exceeds 32 megapixels; downsample explicitly first')
            im=ImageOps.exif_transpose(im).convert('RGB');dest=inputs/f'{i:02d}-photo.png';im.save(dest)
            normalized.append(dest)
            sources.append({'input_name':src.name,'input_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'normalized':str(dest.relative_to(out)),'dimensions':list(im.size),'rights':'user-supplied; retain actual source/license separately'})
    selected=[x for i,x in enumerate(normalized,1) if i not in skip and i not in subject_plans]
    if selected:
        call([sys.executable,ROOT/'scripts/cutout.py',*selected,'--output-dir',cutouts,'--no-crop','--backend',a.backend,'--refine',a.refine])
    for i,item in subject_plans.items():
        command=[sys.executable,ROOT/'scripts/cutout.py',normalized[i-1],'--output-dir',cutouts,'--no-crop','--backend',item['backend'],'--refine',item.get('refine',a.refine)]
        if item['backend']=='sam2':
            prompt=inputs/f'{i:02d}-subject.json'
            prompt.write_text(json.dumps({'subject':item['subject'],'objects':item['objects']},ensure_ascii=False,indent=2)+'\n')
            command+=['--selection-file',prompt]
        if 'instances' in item:command+=['--instances',str(item['instances'])]
        call(command)
    if selected or subject_plans:
        manifest=json.loads((cutouts/'cutouts.json').read_text())
    else:manifest={'assets':[]}
    masks={Path(x['source_file']).resolve():x for x in manifest['assets']}
    scenes=[]
    for i,photo in enumerate(normalized,1):
        scene={'duration':photo_durations[i-1],'photo':str(photo.relative_to(out)),'leadIn':lead_ins[i-1],'position':{'x':.5,'y':.5}}
        if photo in masks:
            item=masks[photo];scene['cutout']=str((cutouts/item['file']).relative_to(out))
            for warning in item['qa']['warnings']:warnings.append({'photo':i,'warning':warning})
            # Solve object-position from the foreground box in source pixels.
            sw,sh=item['width'],item['height'];rw,rh=map(float,a.ratio.split(':'))
            vw,vh=(sh*rw/rh,sh) if sw/sh>rw/rh else (sw,sw*rh/rw)
            x0,y0,x1,y1=item['qa']['foreground_bbox']
            if a.fit=='auto' and (x1-x0>vw*.98 or y1-y0>vh*.98):
                scene['fit']='contain'
                warnings.append({'photo':i,'warning':'subject_requires_contain_for_selected_ratio'})
            else:
                scene['fit']='cover' if a.fit=='auto' else a.fit
                px=max(0,min(1,((x0+x1)/2-vw/2)/(sw-vw))) if sw>vw else .5
                py=max(0,min(1,((y0+y1)/2-vh/2)/(sh-vh))) if sh>vh else .5
                scene['position']={'x':round(px,6),'y':round(py,6)}
        elif a.fit!='auto':scene['fit']=a.fit
        scenes.append(scene)
    edit_report=None
    if a.edit_script:
        from edit_plan import apply_plan, markdown
        planned,edit_report=apply_plan({'style':'cutout-reveal','ratio':a.ratio,'scenes':scenes},script,out)
        scenes=planned['scenes'];bpm=edit_report['bpm'];duration=round(edit_report['duration']+(2 if a.end_title else 0),6)
        photo_durations=[s['duration'] for s in scenes];lead_ins=[s['leadIn'] for s in scenes];timing_mode='edit-script'
        warnings.extend(edit_report['warnings'])
        (out/'edit-script.json').write_text(json.dumps(script,ensure_ascii=False,indent=2)+'\n')
        (out/'EDIT-SCRIPT.md').write_text(markdown(edit_report))
        (out/'edit-review.json').write_text(json.dumps(edit_report,ensure_ascii=False,indent=2)+'\n')
    bgm=None
    if a.demo_music:
        music=inputs/'original-preview-bed.wav'
        call([sys.executable,ROOT/'scripts/music.py','--output',music,'--duration',max(1,duration),'--bpm',bpm])
        bgm={'path':str(music.relative_to(out)),'volume':preset.get('bgmVolume',.45),'fadeIn':.08,'fadeOut':min(.7,duration*.25)}
    elif a.music:
        suffix=a.music.suffix.lower();music=inputs/('user-music'+suffix);shutil.copy2(a.music.expanduser(),music)
        bgm={'path':str(music.relative_to(out)),'volume':preset.get('bgmVolume',.45),'fadeIn':.12,'fadeOut':min(.7,duration*.25)}
    job={'schemaVersion':1,'title':a.title,'style':'cutout-reveal','platform':'tiktok' if a.platform=='douyin' else a.platform,'ratio':a.ratio,'fps':preset.get('fps',30),'grade':a.grade or preset.get('grade','warm-film'),'palette':preset.get('palette',{}),'scenes':scenes}
    caption=a.text if a.text is not None else preset.get('centerText','')
    if caption:job['overlay']={'text':caption,'color':'#ffffff'}
    if a.end_title:job['endCard']={'duration':2,'title':a.end_title,'subtitle':''}
    if bgm:job['bgm']=bgm
    (out/'job.json').write_text(json.dumps(job,ensure_ascii=False,indent=2)+'\n')
    timing={'mode':timing_mode,'pace':pace if timing_mode=='pace' else None,'bpm':bpm,'photo_durations':photo_durations,'requested_lead_in':lead,'lead_in_seconds':lead_ins,'beat_detection':False}
    (out/'sources.json').write_text(json.dumps({'images':sources,'subjects':list(subject_plans.values()),'music':{'mode':'original-procedural-preview' if a.demo_music else 'user-supplied' if a.music else 'none','bpm_grid':bpm if a.demo_music or a.bpm or a.edit_script else None,'beat_detection':False},'timing':timing,'editing':edit_report,'warnings':warnings},ensure_ascii=False,indent=2)+'\n')
    call(['node',ROOT/'scripts/build.mjs','--config',out/'job.json','--out',out/'project'])
    if a.check or a.render:call(['npm','run','check','--','--snapshots'],cwd=out/'project')
    if a.render:call(['npm','run','render','--','--quality','looks','--output',out/'video.mp4'],cwd=out/'project')
    print(json.dumps({'ok':True,'job':str(out/'job.json'),'project':str(out/'project'),'video':str(out/'video.mp4') if a.render else None,'timing':timing,'duration':duration,'warnings':warnings,'visual_review_required':True},ensure_ascii=False,indent=2))
    return 0
if __name__=='__main__':
    try:sys.exit(main())
    except (subprocess.CalledProcessError,ValueError,RuntimeError) as e:
        print(f'Build failed: {e}. Prepared artifacts retained for diagnosis.',file=sys.stderr);sys.exit(1)
