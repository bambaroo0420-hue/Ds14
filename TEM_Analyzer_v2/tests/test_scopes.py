import asyncio
import io
import json
import unittest
import zipfile
import numpy as np
from PIL import Image
import test_workflow
from tem_analyzer.labels import UNKNOWN, EXCLUDED, pack
from tem_analyzer.services.scopes import scope_arrays, scope_reviewed
from tem_analyzer.storage import Project


class ScopeTests(unittest.TestCase):
    setUp=test_workflow.WorkflowTest.setUp
    tearDown=test_workflow.WorkflowTest.tearDown

    def post(self,path,body,status=200):
        r=self.client.post('/api/workflow/'+path,json=body)
        self.assertEqual(r.status_code,status,r.text);return r.json()

    def prepare(self):
        p=self.api.project;m=np.zeros((60,80),bool);m[15:35,10:70]=True
        c=p.put_candidate(self.id,m,'scope-test')
        other=p.put_candidate(self.id,np.ones_like(m),'unselected-unknown')
        self.post('scopes/save',dict(image_id=self.id,candidate_ids=[c['id']]))
        return c,m,other

    def test_unassigned_partial_gt_unknown_and_export(self):
        c,m,_=self.prepare();p=self.api.project
        self.assertIsNone(c['layer_id'])
        self.post('gt/confirm',dict(image_id=self.id,scope_id='target'),400)
        self.post('scopes/confirm',dict(image_id=self.id))
        self.post('gt/confirm',dict(image_id=self.id,scope_id='target'))
        _,labels,valid,_=scope_arrays(p,self.id,'target')
        self.assertTrue((labels[~m]==UNKNOWN).all());np.testing.assert_array_equal(valid,m)
        r=self.client.post('/api/workflow/export',json=dict(image_ids=[self.id],scope_id='target',include_gt=True))
        self.assertEqual(r.status_code,200,r.text)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            saved=np.array(Image.open(io.BytesIO(z.read(self.id+'/partial_gt/labels.png'))))
            np.testing.assert_array_equal(saved,labels)
            self.assertTrue(json.loads(z.read('export_mode.json'))['partial_binary_target'])
        self.assertTrue(scope_reviewed(Project(p.root),self.id,'target'))

    def test_provisional_measurement_without_any_layer_and_unknown_not_background(self):
        c,m,_=self.prepare()
        self.post('rotation/preview',dict(image_id=self.id,config=dict(scope_id='target',mode='edge')))
        self.post('rotation/confirm',dict(image_id=self.id))
        self.client.post('/api/scale/manual',json=dict(image_id=self.id,a=[5,5],b=[55,5],length=100))
        result=self.post('measurement',dict(image_id=self.id,config=dict(scope_id='target',start=30,stop=50,step=10)))
        self.assertEqual(result['summary']['mean'],40)
        self.assertEqual(result['candidate_ids'],[c['id']]);self.assertIsNone(result['layer_id'])
        self.assertEqual(result['review_status'],'provisional_unreviewed_masks')
        self.assertFalse(self.api.project.state['gt_reviews'])

    def test_exclusion_review_staleness_and_deleted_mask_fail_closed(self):
        c,m,_=self.prepare();p=self.api.project
        self.post('scopes/confirm',dict(image_id=self.id))
        ex=np.zeros_like(m);ex[:,30:35]=1;p.state['annotations'][self.id]={'exclude':pack(ex)}
        self.assertFalse(scope_reviewed(p,self.id,'target'))
        _,labels,valid,_=scope_arrays(p,self.id,'target');self.assertTrue((labels[ex]==EXCLUDED).all());self.assertFalse(valid[ex].any())
        p.candidate(self.id,c['id'])['active']=False
        self.post('rotation/preview',dict(image_id=self.id,config={'scope_id':'target'}),400)

    def test_sampling_and_raw_exclusions_export_without_layers(self):
        import csv
        self.prepare()
        self.post('rotation/preview',dict(image_id=self.id,config=dict(scope_id='target')))
        self.post('rotation/confirm',dict(image_id=self.id))
        self.client.post('/api/scale/manual',json=dict(image_id=self.id,a=[5,5],b=[55,5],length=100))
        result=self.post('measurement',dict(image_id=self.id,config=dict(scope_id='target',start=0,stop=79,step=10,sampling=dict(mode='component_center',center_fraction=.5))))
        self.assertEqual(result['summary']['count'],3);self.assertEqual(result['summary']['mean'],40)
        r=self.client.post('/api/workflow/export',json=dict(image_ids=[self.id],scope_id='target'))
        self.assertEqual(r.status_code,200,r.text)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            rows=list(csv.DictReader(io.StringIO(z.read('measurements.csv').decode('utf-8-sig'))))
            excluded=[r for r in rows if r['status']=='outside_component_window']
            self.assertTrue(excluded)
            self.assertTrue(all(r['length_nm']=='' and float(r['raw_length_nm'])==40 for r in excluded))
            self.assertTrue(all(r['layer_id']=='' and r['scope_id']=='target' for r in rows))

    def test_missing_scope_no_fallback_and_undo_restore(self):
        c,m,_=self.prepare();p=self.api.project
        self.post('rotation/preview',dict(image_id=self.id,config={'scope_id':'missing','layer_id':1}),400)
        self.client.delete('/api/images/'+self.id)
        trash=self.client.get('/api/workflow/trash').json()
        self.post('trash/restore',{'trash_id':trash[0]['id']})
        self.assertEqual(p.state['mask_scopes'][self.id]['target']['candidate_ids'],[c['id']])

    def test_batch_partial_gt_multiple_images_missing_scope_fails_only_that_image(self):
        self.prepare();self.post('scopes/confirm',dict(image_id=self.id));p=self.api.project
        b=io.BytesIO();Image.new('RGB',(80,60)).save(b,format='PNG')
        second=p.add_image(b.getvalue(),'no-selection.png')
        manager=self.api.app.state.workflow_jobs
        async def run():
            manager.start([self.id,second],['gt'],{'scope_id':'target'})
            await manager.task
        asyncio.run(run())
        self.assertEqual([r['status'] for r in manager.current['rows']],['done','failed'])
        self.assertIn('선택 집합',manager.current['rows'][1]['error'])

    def test_batch_rotation_then_measurement_on_two_unassigned_targets(self):
        self.prepare();p=self.api.project;b=io.BytesIO();Image.new('RGB',(80,60)).save(b,format='PNG')
        second=p.add_image(b.getvalue(),'second-target.png');m=np.zeros((60,80),bool);m[20:30,10:70]=True
        c=p.put_candidate(second,m,'target-only');p.put_candidate(second,~m,'not-selected')
        self.post('scopes/save',dict(image_id=second,candidate_ids=[c['id']]))
        for iid in (self.id,second):
            self.post('scopes/confirm',dict(image_id=iid))
            self.client.post('/api/scale/manual',json=dict(image_id=iid,a=[5,5],b=[55,5],length=50))
        manager=self.api.app.state.workflow_jobs
        settings=dict(scope_id='target',rotation=dict(scope_id='target'),measurement=dict(scope_id='target',start=30,stop=50,step=10))
        async def run(steps):
            manager.start([self.id,second],steps,settings);await manager.task
        asyncio.run(run(['gt','rotation']))
        self.assertEqual(manager.current['status'],'completed')
        self.post('confirm-many',dict(image_ids=[self.id,second],kind='rotation'))
        asyncio.run(run(['measurement']))
        self.assertEqual(manager.current['status'],'completed')
        self.assertEqual([p.state['measurements'][i]['summary']['mean'] for i in (self.id,second)],[20,10])
        self.assertTrue(all(c['layer_id'] is None for cs in p.state['candidates'].values() for c in cs))


if __name__=='__main__':unittest.main()
