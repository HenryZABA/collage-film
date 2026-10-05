#!/usr/bin/env python3
"""Contour, synthesis and actual MP4 decoding regressions with synthetic assets."""
import hashlib,json,subprocess,tempfile,unittest,wave
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from outline import create_outline
from tropical_music import compose
from export_mobile import export_mobile

class DeliveryTests(unittest.TestCase):
    def test_border_scales_with_subjects_and_preserves_holes_and_source(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);im=Image.new('RGBA',(400,400));draw=ImageDraw.Draw(im)
            draw.rectangle((30,30,230,230),fill='red');draw.rectangle((80,80,150,150),fill=(0,0,0,0));draw.rectangle((290,290,310,310),fill='blue')
            im.save(p/'mask.png');before=hashlib.sha256((p/'mask.png').read_bytes()).hexdigest()
            a=create_outline(p/'mask.png',p/'a.svg',1080,1440,per_component=True)
            b=create_outline(p/'mask.png',p/'b.svg',2880,3840,max_radius=32,per_component=True)
            self.assertEqual(a['paths'],3);self.assertGreater(max(a['component_radii_px']),min(a['component_radii_px'])*5)
            self.assertAlmostEqual(b['radius_px']/a['radius_px'],2880/1080)
            self.assertEqual(hashlib.sha256((p/'mask.png').read_bytes()).hexdigest(),before)
            self.assertIn('fill="none"',(p/'a.svg').read_text())
    def test_tropical_music_has_requested_duration_and_no_clipping(self):
        sr,a=compose(2.7,100);sr2,b=compose(2.7,100);_,c=compose(5.1,100)
        self.assertEqual((sr,sr2,a.shape),(48000,48000,(129600,2)))
        self.assertTrue(np.array_equal(a,b));self.assertEqual(len(c),244800)
        self.assertGreater(float(np.sqrt(np.mean(a**2))),.01);self.assertLessEqual(float(abs(a).max()),.870001)
        self.assertLess(float(abs(a[-1]).max()),.001)
    def test_mobile_export_decodes_all_frames_and_preserves_ratio(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);source=p/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=1200x1600:rate=30:duration=0.6','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=0.6','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
            r=export_mobile(source,p/'mobile.mp4')
            self.assertEqual((r['width'],r['height'],r['decoded_frames'],r['level']),(1080,1440,18,41))
            with self.assertRaisesRegex(ValueError,'exists'):export_mobile(source,p/'mobile.mp4')
            info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(p/'mobile.mp4')]))
            self.assertEqual(next(s for s in info['streams'] if s['codec_type']=='audio')['codec_name'],'aac')
if __name__=='__main__':unittest.main()
