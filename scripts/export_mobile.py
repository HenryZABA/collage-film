#!/usr/bin/env python3
"""Export an MP4 with bounded mobile decoding cost and verify decoded timestamps."""
import argparse,hashlib,json,math,subprocess
from pathlib import Path

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)]))

def export_mobile(source,output):
    source=Path(source).resolve();output=Path(output).resolve();report=output.with_suffix('.export.json')
    if output.suffix.lower()!='.mp4':raise ValueError('Mobile output must use .mp4')
    if output.exists() or report.exists():raise ValueError('Output/report exists; choose a new filename')
    info=probe(source);video=next(s for s in info['streams'] if s['codec_type']=='video')
    if video.get('color_transfer') in ('smpte2084','arib-std-b67'):raise ValueError('Tone-map HDR to SDR before mobile export; this tool does not relabel HDR as SDR')
    factor=min(1,1080/min(video['width'],video['height']),1920/max(video['width'],video['height']))
    width=max(2,math.floor(video['width']*factor/2)*2);height=max(2,math.floor(video['height']*factor/2)*2)
    if video.get('sample_aspect_ratio','1:1') not in ('1:1','N/A'):raise ValueError('Normalize non-square source pixels before export')
    output.parent.mkdir(parents=True,exist_ok=True)
    args=['ffmpeg','-hide_banner','-v','warning','-n','-i',str(source),'-map','0:v:0','-map','0:a:0?', '-vf',f'scale={width}:{height}:flags=lanczos:out_color_matrix=bt709,setsar=1,fps=30','-c:v','libx264','-preset','slow','-crf','19','-profile:v','high','-level:v','4.1','-pix_fmt','yuv420p','-maxrate','6M','-bufsize','12M','-g','60','-keyint_min','30','-sc_threshold','0','-fps_mode','cfr','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart',str(output)]
    subprocess.run(args,check=True)
    checked=probe(output);v=next(s for s in checked['streams'] if s['codec_type']=='video')
    if (v['width'],v['height'],v['pix_fmt'],v['level'],v['avg_frame_rate'])!=(width,height,'yuv420p',41,'30/1'):raise ValueError('Unexpected output encoding')
    frames=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(output)]))['frames']
    pts=[float(f['best_effort_timestamp_time']) for f in frames]
    if not pts or any(abs(t-i/30)>2e-6 for i,t in enumerate(pts)):raise ValueError('Output is not a continuous 30fps timestamp grid')
    expected=round(float(video['duration'])*30)
    if abs(len(pts)-expected)>1:raise ValueError('Decoded frame count does not match source duration')
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(output),'-f','null','-'],check=True)
    data=output.read_bytes()
    if data.index(b'moov')>data.index(b'mdat'):raise ValueError('MP4 metadata must precede media payload')
    value={'status':'technical PASS; visual and target-device playback review required','source':source.name,'output':output.name,'width':width,'height':height,'fps':30,'decoded_frames':len(pts),'source_duration':float(video['duration']),'duration':float(v['duration']),'codec':v['codec_name'],'profile':v['profile'],'level':v['level'],'video_bitrate':int(v.get('bit_rate',0)),'size_bytes':output.stat().st_size,'sha256':hashlib.sha256(data).hexdigest(),'faststart':True,'encoding_args':args[args.index('-vf'):],'color_policy':'SDR BT709 output; PQ/HLG inputs rejected'}
    report.write_text(json.dumps(value,indent=2)+'\n');return value

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:print(json.dumps(export_mobile(a.input,a.output),indent=2))
    except (ValueError,OSError,KeyError,StopIteration,subprocess.CalledProcessError) as e:p.error(str(e))
if __name__=='__main__':main()
