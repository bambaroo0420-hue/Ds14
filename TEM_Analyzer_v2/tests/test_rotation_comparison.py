import asyncio,copy,io,json,tempfile,unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
import test_workflow
from tem_analyzer.storage import Project
from tem_analyzer.jobs.manager import JobManager
from tem_analyzer.services.scopes import save_scope


class RotationComparisonTests(unittest.TestCase):
    setUp=test_workflow.WorkflowTest.setUp
    tearDown=test_workflow.WorkflowTest.tearDown

    def setup_scope(self):
        p=self.api.project;m=np.zeros((60,80),bool);m[20:35,10:70]=True
        c=p.put_candidate(self.id,m,'fixture',prompts={'points':[[20,27,1],[60,27,1],[40,40,0]]})
        save_scope(p,self.id,'target',[c['id']]);p.save();return p,c

    def test_compare_is_read_only_and_failures_are_rows(self):
        p,c=self.setup_scope();cfg=dict(scope_id='target',mode='auto',edge='top',points=[])
        self.client.post('/api/workflow/rotation/preview',json={'image_id':self.id,'config':cfg})
        self.client.post('/api/workflow/rotation/confirm',json={'image_id':self.id})
        before=copy.deepcopy(p.state);disk=p.path.read_bytes();undo=len(p.state['history'])
        with patch('tem_analyzer.algorithms.orientation.image_direction',side_effect=ValueError('no texture')):
            r=self.client.post('/api/workflow/rotation/compare',json={'image_id':self.id,'config':cfg})
        self.assertEqual(r.status_code,200,r.text);out=r.json()
        self.assertEqual(p.state,before);self.assertEqual(p.path.read_bytes(),disk);self.assertEqual(len(p.state['history']),undo)
        self.assertTrue(any(row['status']=='failed' and 'no texture' in row['error'] for row in out['rows']))
        pt=next(row for row in out['rows'] if 'SAM' in row['name']);self.assertEqual(pt['point_count'],2)
        self.assertEqual(pt['config']['points'],[[20,27],[60,27]]);self.assertTrue(pt['needs_review']);self.assertTrue(pt['warnings'])
        self.assertEqual(c['layer_id'],None);self.assertTrue(p.state['alignments'][self.id]['confirmed'])

    def test_missing_scope_errors_and_no_silent_layer_fallback(self):
        self.setup_scope();r=self.client.post('/api/workflow/rotation/compare',json={'image_id':self.id,'config':{'scope_id':'missing'}})
        self.assertEqual(r.status_code,400);self.assertIn('선택 집합',r.text)

    def test_comparison_selection_still_requires_confirmation(self):
        p,_=self.setup_scope();cfg=dict(scope_id='target',mode='auto',edge='top',points=[])
        with patch('tem_analyzer.algorithms.orientation.image_direction',side_effect=ValueError('no texture')):
            out=self.client.post('/api/workflow/rotation/compare',json={'image_id':self.id,'config':cfg}).json()
        chosen=next(row for row in out['rows'] if 'SAM' in row['name'])
        r=self.client.post('/api/workflow/rotation/preview',json={'image_id':self.id,'config':chosen['config']})
        self.assertEqual(r.status_code,200,r.text);self.assertFalse(r.json()['confirmed'])
        r=self.client.post('/api/workflow/measurement',json={'image_id':self.id,'config':{'scope_id':'target'}})
        self.assertEqual(r.status_code,400);self.assertIn('회전 결과',r.text)


class BatchSkippedTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_image_marks_downstream_skipped_and_continues(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Project(folder);b=io.BytesIO();Image.new('RGB',(30,30)).save(b,format='PNG')
            ids=[p.add_image(b.getvalue(),str(i)+'.png') for i in range(2)];calls=[]
            def execute(iid,stage,settings):
                calls.append((iid,stage))
                if iid==ids[0] and stage=='gt':raise ValueError('needs mask review')
                return {'ok':True}
            mgr=JobManager(p,asyncio.Lock(),execute);mgr.start(ids,['gt','rotation','measurement'],{});await mgr.task
            j=mgr.current;self.assertEqual(j['status'],'completed_with_errors');self.assertEqual(j['done'],6);self.assertEqual(j['total'],6)
            self.assertEqual([r['status'] for r in j['rows']],['failed','skipped','skipped','done','done','done'])
            self.assertEqual(j['rows'][1]['blocked_by'],'gt');self.assertNotIn((ids[0],'rotation'),calls)
            self.assertEqual(Project(folder).state['jobs'][-1]['rows'],j['rows'])

    async def test_cancel_does_not_claim_unstarted_work_done(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Project(folder);b=io.BytesIO();Image.new('RGB',(30,30)).save(b,format='PNG');iid=p.add_image(b.getvalue(),'a.png')
            def execute(*args):raise AssertionError('must not execute')
            mgr=JobManager(p,asyncio.Lock(),execute);mgr.start([iid],['rotation','measurement'],{});mgr.cancel();await mgr.task
            self.assertEqual(mgr.current['status'],'cancelled');self.assertEqual(mgr.current['done'],0);self.assertEqual(mgr.current['rows'],[])
