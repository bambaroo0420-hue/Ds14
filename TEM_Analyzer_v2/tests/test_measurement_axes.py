import asyncio,copy,csv,io,json,unittest,zipfile
import numpy as np
import test_workflow
from tem_analyzer.storage import Project
from tem_analyzer.services.scopes import save_scope


class MeasurementAxesTests(unittest.TestCase):
    setUp=test_workflow.WorkflowTest.setUp
    tearDown=test_workflow.WorkflowTest.tearDown

    def post(self,path,body):
        r=self.client.post('/api/'+path,json=body);self.assertEqual(r.status_code,200,r.text);return r

    def ready(self):
        p=self.api.project;m=np.zeros((60,80),bool);m[20:40,10:70]=True;c=p.put_candidate(self.id,m,'fixture')
        save_scope(p,self.id,'target',[c['id']]);p.save()
        self.post('workflow/rotation/preview',dict(image_id=self.id,config=dict(scope_id='target',mode='auto')))
        self.post('workflow/rotation/confirm',dict(image_id=self.id))
        self.post('scale/manual',dict(image_id=self.id,a=[5,5],b=[55,5],length=50));return p,c

    def measure(self,axis):
        return self.post('workflow/measurement',dict(image_id=self.id,config=dict(scope_id='target',axis=axis,start=25,stop=35,step=5))).json()

    def export(self,both=True):
        return self.post('workflow/export',dict(image_ids=[self.id],scope_id='target',export_all_axes=both))

    def test_two_axes_preserved_export_and_legacy_latest(self):
        p,c=self.ready();th=self.measure('thickness');cd=self.measure('cd')
        self.assertEqual((th['summary']['mean'],cd['summary']['mean']),(20,60))
        self.assertEqual(p.state['measurements'][self.id]['axis'],'cd');self.assertEqual(set(p.state['measurements_by_axis'][self.id]),{'thickness','cd'})
        with zipfile.ZipFile(io.BytesIO(self.export().content)) as z:
            self.assertEqual(json.loads(z.read(self.id+'/measurement.json'))['axis'],'cd')
            for axis in ('thickness','cd'):self.assertEqual(json.loads(z.read(self.id+'/measurements/'+axis+'.json'))['axis'],axis)
            rows=list(csv.DictReader(io.StringIO(z.read('measurements.csv').decode('utf-8-sig'))));self.assertEqual({r['axis'] for r in rows},{'thickness','cd'});self.assertEqual(len(rows),6)
        with zipfile.ZipFile(io.BytesIO(self.export(False).content)) as z:
            rows=list(csv.DictReader(io.StringIO(z.read('measurements.csv').decode('utf-8-sig'))));self.assertEqual({r['axis'] for r in rows},{'cd'})
        self.assertIsNone(c['layer_id'])

    def test_stale_other_axis_blocks_combined_not_current_latest(self):
        p,_=self.ready();self.measure('thickness');self.measure('cd')
        self.post('scale/manual',dict(image_id=self.id,a=[5,5],b=[55,5],length=100));self.measure('thickness')
        r=self.client.post('/api/workflow/export',json=dict(image_ids=[self.id],scope_id='target',export_all_axes=True))
        self.assertEqual(r.status_code,400);self.assertIn('cd',r.text);self.assertIn('만료',r.text)
        self.export(False)
        status=self.client.get('/api/workflow/status/'+self.id).json()['measurement_axes'];self.assertTrue(status['cd']['stale']);self.assertFalse(status['thickness']['stale'])

    def test_export_does_not_change_state_disk_or_undo(self):
        p,_=self.ready();self.measure('thickness');self.measure('cd');before=copy.deepcopy(p.state);disk=p.path.read_bytes()
        self.export();self.assertEqual(p.state,before);self.assertEqual(p.path.read_bytes(),disk)

    def test_reopen_undo_redo_and_image_restore_preserve_axes(self):
        p,_=self.ready();self.measure('thickness');self.measure('cd')
        self.assertEqual(set(Project(self.temp.name).state['measurements_by_axis'][self.id]),{'thickness','cd'})
        self.post('v2/undo',{});self.assertEqual(set(p.state['measurements_by_axis'][self.id]),{'thickness'})
        self.post('v2/redo',{});self.assertEqual(set(p.state['measurements_by_axis'][self.id]),{'thickness','cd'})
        r=self.client.delete('/api/images/'+self.id);self.assertEqual(r.status_code,200)
        self.assertNotIn(self.id,p.state['measurements_by_axis']);trash=self.client.get('/api/workflow/trash').json()[0]['id']
        self.post('workflow/trash/restore',{'trash_id':trash});self.assertEqual(set(p.state['measurements_by_axis'][self.id]),{'thickness','cd'});self.export()

    def test_legacy_latest_migrates_when_other_axis_measured(self):
        p,_=self.ready();th=self.measure('thickness');p.state.pop('measurements_by_axis');p.save()
        status=self.client.get('/api/workflow/status/'+self.id).json();self.assertEqual(set(status['measurement_axes']),{'thickness'})
        self.measure('cd');self.assertEqual(p.state['measurements_by_axis'][self.id]['thickness'],th)

    def test_incompatible_scope_and_invalid_option_rejected(self):
        p,c=self.ready();self.measure('thickness');self.measure('cd')
        r=self.client.post('/api/workflow/export',json=dict(image_ids=[self.id],export_all_axes=True));self.assertEqual(r.status_code,400)
        r=self.client.post('/api/workflow/export',json=dict(image_ids=[self.id],scope_id='target',export_all_axes='yes'));self.assertEqual(r.status_code,400)

    def test_batch_measurements_preserve_each_axis(self):
        p,_=self.ready();manager=self.api.app.state.workflow_jobs
        async def run():
            for axis in ('thickness','cd'):
                manager.start([self.id],['measurement'],{'measurement':dict(scope_id='target',axis=axis,start=25,stop=35,step=5)})
                await manager.task
                self.assertEqual(manager.current['status'],'completed')
        asyncio.run(run())
        self.assertEqual({a:m['summary']['mean'] for a,m in p.state['measurements_by_axis'][self.id].items()},{'thickness':20,'cd':60})
        self.export()
