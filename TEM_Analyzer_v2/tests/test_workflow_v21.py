import asyncio
import copy
import io
import json
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import numpy as np
from PIL import Image
import test_workflow
from tem_analyzer.storage import Project
from tem_analyzer.services.layers import inspect_conflicts,propose_boundaries,apply_boundaries,unions
from tem_analyzer.algorithms.annotations import propose_annotations
from tem_analyzer.jobs.manager import JobManager


class Workflow21Tests(unittest.TestCase):
    setUp=test_workflow.WorkflowTest.setUp
    tearDown=test_workflow.WorkflowTest.tearDown

    def post(self,path,body):
        r=self.client.post('/api/workflow/'+path,json=body)
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def rectangle(self,lid=1,ys=(15,35),xs=(10,70),reviewed=False):
        p=self.api.project;m=np.zeros((60,80),bool);m[ys[0]:ys[1],xs[0]:xs[1]]=True
        if lid not in [x['id'] for x in p.state['layers']]:p.state['layers'].append(dict(id=lid,name=str(lid),color='#ee7755',locked=False))
        c=p.put_candidate(self.id,m,'fixture');c.update(layer_id=lid,reviewed=reviewed);p.save();return c,m

    def test_bulk_assign_review_separate_and_undo(self):
        c,m=self.rectangle();c['layer_id']=None;p=self.api.project;p.save()
        self.post('masks/bulk',dict(image_id=self.id,candidate_ids=[c['id']],action='assign',layer_id=1))
        self.assertFalse(c['reviewed'])
        self.post('masks/bulk',dict(image_id=self.id,candidate_ids=[c['id']],action='review'))
        self.assertTrue(c['reviewed'])
        self.post('masks/bulk',dict(image_id=self.id,candidate_ids=[c['id']],action='delete'))
        self.assertEqual(self.client.post('/api/v2/undo',json={}).status_code,200)
        self.assertFalse(p.candidate(self.id,c['id'])['deleted'])

    def test_nonadjacent_overlap_blocks_review_and_export(self):
        c,m=self.rectangle();self.rectangle(2,(40,50));self.rectangle(3,(20,30))
        report=inspect_conflicts(self.api.project,self.id)
        self.assertTrue(any(not p['adjacent'] and p['overlap_pixels'] for p in report['pairs']))
        self.assertEqual(self.client.post('/api/workflow/masks/bulk',json=dict(image_id=self.id,candidate_ids=[c['id']],action='review')).status_code,400)
        self.assertEqual(self.client.post('/api/workflow/export',json={'image_ids':[self.id]}).status_code,400)

    def test_measurement_review_gates_stale_detection_and_export(self):
        c,m=self.rectangle(reviewed=True)
        cfg=dict(layer_id=1,mode='edge',edge='top')
        rot=self.post('rotation/preview',dict(image_id=self.id,config=cfg))
        self.assertAlmostEqual(rot['transform']['angle_deg'],0)
        mc=dict(layer_id=1,axis='thickness',start=30,stop=50,step=10)
        self.assertEqual(self.client.post('/api/workflow/measurement',json=dict(image_id=self.id,config=mc)).status_code,400)
        self.post('rotation/confirm',{'image_id':self.id})
        self.client.post('/api/scale/manual',json=dict(image_id=self.id,a=[5,5],b=[55,5],length=100,unit='nm'))
        value=self.post('measurement',dict(image_id=self.id,config=mc))
        self.assertAlmostEqual(value['summary']['mean'],40)
        r=self.client.post('/api/workflow/export',json={'image_ids':[self.id]});self.assertEqual(r.status_code,200,r.text)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            self.assertIn('measurements.csv',z.namelist());self.assertIn(self.id+'/alignment.json',z.namelist())
            labels=np.array(Image.open(io.BytesIO(z.read(self.id+'/aligned_labels.png'))))
            self.assertEqual(labels.dtype,np.uint16)
        self.api.project.candidate(self.id,c['id'])['reviewed']=False;self.api.project.save()
        status=self.client.get('/api/workflow/status/'+self.id).json()
        self.assertTrue(status['rotation_stale']);self.assertTrue(status['measurement_stale'])

    def test_deleted_image_restore_preserves_masks_and_scale(self):
        c,m=self.rectangle(reviewed=True);p=self.api.project
        self.client.post('/api/scale/manual',json=dict(image_id=self.id,a=[5,5],b=[55,5],length=50))
        self.client.delete('/api/images/'+self.id)
        trash=self.client.get('/api/workflow/trash').json();self.assertEqual(len(trash),1)
        self.post('trash/restore',{'trash_id':trash[0]['id']})
        np.testing.assert_array_equal(p.mask(self.id,c['id']),m)
        self.assertEqual(p.state['scale'][self.id]['nm_per_px'],1)
        reloaded=Project(self.temp.name);self.assertIn(self.id,reloaded.state['images'])

    def test_whole_image_annotations_without_template_and_cache_state(self):
        image=np.full((200,400,3),25,np.uint8);image[155:159,20:120]=255
        words=[dict(text='50 nm',box=[30,130,100,150],confidence=.99),dict(text='120 k',box=[10,5,80,25],confidence=.95),dict(text='Sample A',box=[10,180,330,196],confidence=.9)]
        p=propose_annotations(image,words)
        self.assertAlmostEqual(p['scale']['nm_per_px'],.5)
        self.assertEqual({r['kind'] for r in p['regions']},{'scale','magnification','footer'})
        with patch('tem_analyzer.ocr.read_words',return_value=[]):
            self.post('annotations/detect',{'image_id':self.id})
        self.post('annotations/apply',{'image_id':self.id})
        self.assertFalse(self.api.project.state['scale'][self.id]['confirmed'])

    def test_boundary_pair_updates_both_keeps_unknown_and_stales_preview(self):
        a,am=self.rectangle(1,(10,25));b,bm=self.rectangle(2,(25,45));p=self.api.project
        proposal=propose_boundaries(p,self.id,{'radius':3,'max_gap':0})
        outside=~(am|bm)
        for m in proposal['masks'].values():self.assertFalse((m&outside).any())
        self.assertFalse((proposal['masks'][1]&proposal['masks'][2]).any())
        a['name']='changed'
        with self.assertRaises(ValueError):apply_boundaries(p,self.id,proposal)

    def test_bulk_lock_preflight_is_atomic(self):
        a,_=self.rectangle(1,(10,20));b,_=self.rectangle(2,(30,40));p=self.api.project
        p.state['layers'][1]['locked']=True;p.save()
        result=self.client.post('/api/workflow/masks/bulk',json=dict(image_id=self.id,candidate_ids=[a['id'],b['id']],action='delete'))
        self.assertEqual(result.status_code,400);self.assertFalse(p.candidate(self.id,a['id'])['deleted'])

    def test_no_gt_or_boundary_required_for_rotation_and_provisional_measurement(self):
        c,_=self.rectangle(reviewed=False)
        rot=self.post('rotation/preview',dict(image_id=self.id,config={'layer_id':1}))
        self.assertFalse(rot['mask_reviewed']);self.assertFalse(self.api.project.state['gt_reviews'])
        self.post('rotation/confirm',{'image_id':self.id})
        self.client.post('/api/scale/manual',json=dict(image_id=self.id,a=[5,5],b=[55,5],length=100))
        value=self.post('measurement',dict(image_id=self.id,config=dict(layer_id=1,start=30,stop=50,step=10)))
        self.assertEqual(value['review_status'],'provisional_unreviewed_masks');self.assertAlmostEqual(value['summary']['mean'],40)
        r=self.client.post('/api/workflow/export',json={'image_ids':[self.id]});self.assertEqual(r.status_code,200,r.text)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:self.assertNotIn(self.id+'/gt.zip',z.namelist())
        self.assertEqual(self.client.post('/api/workflow/export',json={'image_ids':[self.id],'include_gt':True}).status_code,400)

    def test_legacy_disabled_but_ocr_regions_always_active(self):
        from tem_analyzer.preprocessing import exclusion_mask
        p=self.api.project;r=p.state['preprocessing'][self.id]
        r['template']={'scale_roi':None,'text_rois':[[.8,0,1,.2]]}
        r['auto_regions']={'scale_roi':[0,.8,.3,1],'text_rois':[[0,0,.2,.2]]}
        ex=exclusion_mask(p,self.id);self.assertFalse(ex[5,75]);self.assertTrue(ex[5,5]);self.assertTrue(ex[55,5])
        self.post('templates/enabled',{'enabled':True});self.assertTrue(exclusion_mask(p,self.id)[5,75])
        self.post('templates/enabled',{'enabled':False});self.assertFalse(exclusion_mask(p,self.id)[5,75]);self.assertTrue(exclusion_mask(p,self.id)[5,5])
        self.assertFalse(Project(self.temp.name).state['legacy_templates_enabled'])

    def test_scale_does_not_pair_with_glyph_and_handles_rotated_bar(self):
        image=np.full((200,400,3),25,np.uint8);image[155:159,20:120]=255;image[140:142,45:61]=255
        words=[dict(text='50 nm',box=[30,130,100,150],confidence=.99)]
        self.assertAlmostEqual(propose_annotations(image,words)['scale']['nm_per_px'],.5)
        from tem_analyzer.calibration import bar_candidates
        rotated=np.array(Image.fromarray(image).rotate(7,resample=Image.Resampling.BICUBIC,expand=True))
        bars=bar_candidates(rotated,[0,0,1,1]);self.assertAlmostEqual(bars[0]['pixel_length'],100,delta=2)
        words[0]['box'][3]=156  # OCR padding can include the top pixel of the actual bar.
        self.assertAlmostEqual(propose_annotations(image,words)['scale']['nm_per_px'],.5)

    def test_auto_rotation_uses_objects_for_multiple_masks(self):
        self.rectangle(1,(10,25),(5,25));self.rectangle(1,(14,29),(40,60))
        r=self.post('rotation/preview',dict(image_id=self.id,config={'layer_id':1,'mode':'auto'}))
        self.assertEqual(r['resolved_mode'],'objects')
        self.assertAlmostEqual(r['transform']['angle_deg'],-np.degrees(np.arctan(4/35)),places=6)
        self.assertEqual(len(r['fit']['points']),2);self.assertFalse(r['mask_reviewed'])


class BatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_serial_partial_failure_cancel_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Project(folder);buf=io.BytesIO();Image.new('RGB',(30,30)).save(buf,format='PNG')
            ids=[p.add_image(buf.getvalue(),str(i)+'.png') for i in range(3)]
            visited=[]
            def execute(iid,stage,settings):
                visited.append((iid,stage))
                if iid==ids[1]:raise ValueError('controlled image failure')
                return {'ok':True}
            manager=JobManager(p,asyncio.Lock(),execute)
            manager.start(ids,['sam'],{});await manager.task
            self.assertEqual(manager.current['status'],'completed_with_errors');self.assertEqual(len(visited),3)
            manager.start(ids,['sam','measurement'],{});manager.cancel();await manager.task
            self.assertEqual(manager.current['status'],'cancelled')
            self.assertFalse(p.busy_job)
            p.state['jobs'][-1]['status']='running';p.save();q=Project(folder)
            JobManager(q,asyncio.Lock(),execute);self.assertEqual(q.state['jobs'][-1]['status'],'interrupted')


if __name__=='__main__':unittest.main()
