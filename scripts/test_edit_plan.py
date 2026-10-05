#!/usr/bin/env python3
"""Meaningful geometry and source-binding regressions, without models or network."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from edit_plan import apply_plan

class EditPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        Image.new('RGB',(1080,1920),'blue').save(self.base/'photo.png')
        mask=Image.new('RGBA',(1080,1920),(0,0,0,0));mask.paste((255,255,255,255),(400,1300,600,1500));mask.save(self.base/'cutout.png')
        self.job={'style':'cutout-reveal','ratio':'9:16','scenes':[{'photo':'photo.png','cutout':'cutout.png','duration':.6} for _ in range(3)]}
        self.shot={'source_index':1,'source_sha256':hashlib.sha256((self.base/'photo.png').read_bytes()).hexdigest(),'role':'wide','connection':'start','quality_note':'intentional wide shot','beats':1,'zoom':1}
        self.script={'schema_version':1,'story':'Travel fragments','bpm':100,'shots':[dict(self.shot,source_index=i) for i in range(1,4)]}
    def tearDown(self):self.tmp.cleanup()
    def test_order_omission_and_timing_are_executed(self):
        self.script['shots']=[dict(self.shot,source_index=3,beats=2),dict(self.shot,source_index=1)]
        job,r=apply_plan(self.job,self.script,self.base)
        self.assertEqual([s['source_index'] for s in r['shots']],[3,1]);self.assertEqual(r['omitted_source_indices'],[2]);self.assertAlmostEqual(r['duration'],1.8);self.assertEqual(job['scenes'][0]['duration'],1.2)
        self.assertEqual(job['scenes'][0]['leadIn'],0);self.assertEqual(job['scenes'][1]['leadIn'],.2)
    def test_changed_photo_cannot_reuse_old_plan(self):
        self.script['shots'][0]['source_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'does not match'):apply_plan(self.job,self.script,self.base)
    def test_subject_anchor_and_size_geometry(self):
        self.script['shots'][0].update(zoom=1.2,anchor={'x':.5,'y':.7})
        job,r=apply_plan(self.job,self.script,self.base);s=r['shots'][0];box=s['subject_bounds']
        self.assertAlmostEqual((box[0]+box[2])/2,.5,places=4);self.assertAlmostEqual((box[1]+box[3])/2,.7,places=4)
        self.assertAlmostEqual(s['subject_height_fraction'],200*1.2/1920,places=4)
        self.assertAlmostEqual(job['scenes'][0]['framing']['x'],.044444,places=6)
    def test_anchor_is_limited_to_keep_background_covering_canvas(self):
        self.script['shots'][0].update(zoom=1.1,anchor={'x':.95,'y':.05})
        job,r=apply_plan(self.job,self.script,self.base)
        f=job['scenes'][0]['framing'];self.assertLessEqual(abs(f['x']),.050001);self.assertLessEqual(abs(f['y']),.050001)
        self.assertIn('anchor_limited_by_full_frame_coverage',[w['code'] for w in r['warnings']])
    def test_small_run_and_pixel_upscale_reported(self):
        _,r=apply_plan(self.job,self.script,self.base);self.assertIn('three_small_subjects_in_a_row',[w['code'] for w in r['warnings']])
        self.script['shots'][0]['zoom']=2
        _,r=apply_plan(self.job,self.script,self.base);self.assertIn('pixel_upscale',[w['code'] for w in r['warnings']]);self.assertIn('subject_cropped',[w['code'] for w in r['warnings']])
    def test_duplicate_sources_and_nonfinite_zoom_rejected(self):
        self.script['shots'][1]['source_index']=1
        with self.assertRaises(ValueError):apply_plan(self.job,self.script,self.base)
        self.script['shots'][1]['source_index']=2;self.script['shots'][0]['zoom']=float('nan')
        with self.assertRaises(ValueError):apply_plan(self.job,self.script,self.base)
    def test_does_not_mutate_source_job(self):
        before=copy.deepcopy(self.job);apply_plan(self.job,self.script,self.base);self.assertEqual(before,self.job)
if __name__=='__main__':unittest.main()
