import io,json,unittest,zipfile,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import test_workflow
from tem_analyzer.storage import Project
from tem_analyzer.labels import compose,pack,UNKNOWN,UNCERTAIN,EXCLUDED
from tem_analyzer.boundary import refine_all,topology
from tem_analyzer.v2_api import metric

class V2Tests(unittest.TestCase):
    setUp=test_workflow.WorkflowTest.setUp
    tearDown=test_workflow.WorkflowTest.tearDown
    def candidate(self,layer=1):
        m=np.zeros((60,80),bool);m[15:40,20:50]=1;c=self.api.project.put_candidate(self.id,m,'fixture');c.update(layer_id=layer,instance_id='cell_7',reviewed=True);self.api.project.save();return c,m
    def post(self,path,body):
        r=self.client.post('/api/'+path,json=body);self.assertEqual(r.status_code,200,r.text);return r.json()
    def test_replace_restart_undo_redo_and_soft_delete(self):
        c,m=self.candidate();x=self.post('candidates/brush',{'image_id':self.id,'candidate_id':c['id'],'strokes':[{'mode':'remove','radius':2,'points':[[30,25]]}]})
        self.assertNotIn(self.id,self.api.project.state['protected'])
        self.post('layers/assign',{'image_id':self.id,'candidate_id':x['id'],'layer_id':1,'instance_id':'cell_7','reviewed':True,'mode':'replace'})
        self.assertFalse(self.api.project.candidate(self.id,c['id'])['active']);labels,_,conflict=compose(self.api.project,self.id);self.assertFalse(conflict.any());self.assertEqual(labels[25,30],UNKNOWN)
        p=Project(self.temp.name);p.undo();self.assertTrue(p.candidate(self.id,c['id'])['active']);p=Project(self.temp.name);p.undo(True);self.assertFalse(p.candidate(self.id,c['id'])['active'])
        self.assertTrue(p.mask(self.id,c['id']).any());self.assertEqual(p.candidate(self.id,x['id'])['instance_id'],'cell_7')
    def test_lock_and_protection_preview(self):
        c,m=self.candidate();self.post('v2/lock',{'layer_id':1,'locked':True})
        r=self.client.post('/api/candidates/brush',json={'image_id':self.id,'candidate_id':c['id'],'strokes':[]});self.assertEqual(r.status_code,400)
        r=self.client.delete(f'/api/candidates/{self.id}/{c["id"]}');self.assertEqual(r.status_code,400)
        self.post('v2/annotations',{'image_id':self.id,'kind':'exclude','strokes':[{'mode':'add','radius':3,'points':[[30,25]]}]})
        labels,_,_=compose(self.api.project,self.id);self.assertEqual(labels[25,30],1)
    def test_delete_rollback_and_partial_result(self):
        c,m=self.candidate();p=self.api.project
        import tem_analyzer.storage as storage
        original=storage.os.replace;count=0
        def broken(src,dst):
            nonlocal count
            if str(dst).endswith('.png') and 'trash' in str(dst):
                count+=1
                if count==2:raise PermissionError('simulated file lock')
            return original(src,dst)
        with patch.object(storage.os,'replace',side_effect=broken):
            r=self.post('v2/delete',{'image_ids':[self.id,'missing']})
        self.assertEqual(r['count'],0);self.assertIn(self.id,r['failed']);np.testing.assert_array_equal(p.mask(self.id,c['id']),m);self.assertTrue((p.root/'images'/f'{self.id}.png').exists())
        restored=Project(self.temp.name);self.assertIn(self.id,restored.state['images'])
    def test_invalid_mutation_does_not_create_history(self):
        before=json.loads(self.api.project.path.read_text());r=self.client.post('/api/v2/filters',json={'image_id':self.id,'branch':'sam','config':{'sigma':20}});self.assertEqual(r.status_code,400)
        self.assertEqual(json.loads(self.api.project.path.read_text()),before)
    def test_annotations_export_validity_and_metrics(self):
        c,m=self.candidate();p=self.api.project
        for kind,point in [('background',[5,5]),('uncertain',[30,25]),('exclude',[70,45])]:self.post('v2/annotations',{'image_id':self.id,'kind':kind,'strokes':[{'mode':'add','radius':2,'points':[point]}]})
        r=self.client.get(f'/api/v2/export/{self.id}.zip');self.assertEqual(r.status_code,200)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            self.assertEqual(set(z.namelist()),{'image.png','labels.png','semantic.png','lab_mask.png','valid.png','edge.png','center.png','metadata.json'})
            arr=lambda n:np.asarray(Image.open(io.BytesIO(z.read(n+'.png'))))
            labels=arr('labels');valid=arr('valid');self.assertEqual(labels[25,30],UNCERTAIN);self.assertEqual(labels[45,70],EXCLUDED);self.assertEqual(labels[0,0],UNKNOWN);self.assertEqual(labels[5,5],0);self.assertEqual(valid[5,5],255);self.assertEqual(valid[0,0],0);self.assertEqual(valid[25,30],0)
        exact=metric(m,m,np.ones(m.shape,bool));self.assertEqual(exact['iou'],1);self.assertEqual(exact['boundary_f1'],1)
        x=np.roll(m,3,axis=1);shifted=metric(x,m,np.ones(m.shape,bool),1);self.assertLess(shifted['boundary_f1'],1);self.assertGreater(shifted['mean_boundary_distance_px'],0)
    def test_shared_boundary_atomic_apply_and_stale_preview(self):
        a,am=self.candidate();p=self.api.project;bm=np.zeros_like(am);bm[15:40,50:70]=1
        self.post('layers',{'id':2,'name':'B'});b=p.put_candidate(self.id,bm,'fixture');b.update(layer_id=2,instance_id='cell_7',reviewed=True);p.save()
        new=am.copy();new[20:35,50:52]=1
        args={'image_id':self.id,'candidate_id':a['id'],'neighbor_id':b['id'],'settings':{'inside':4,'outside':4}}
        with patch('tem_analyzer.v2_api.refine_all',return_value={'mask':new,'loops':[],'settings':args['settings']}):d=self.post('v2/boundary/preview',args)
        x=self.post('v2/boundary/apply',{'token':d['token']});na,nb=[p.mask(self.id,c['id']) for c in x['created']]
        np.testing.assert_array_equal(na|nb,am|bm);self.assertFalse((na&nb).any());self.assertEqual(x['created'][1]['instance_id'],'cell_7');self.assertFalse(p.candidate(self.id,a['id'])['active'])
        self.post('v2/undo',{});np.testing.assert_array_equal(p.mask(self.id,a['id']),am)
        with patch('tem_analyzer.v2_api.refine_all',return_value={'mask':new,'loops':[],'settings':args['settings']}):d=self.post('v2/boundary/preview',args)
        self.post('candidates/name',{'image_id':self.id,'candidate_id':a['id'],'name':'changed'})
        self.assertEqual(self.client.post('/api/v2/boundary/apply',json={'token':d['token']}).status_code,400)
    def test_seed_reuse_and_run_metadata_without_model_weights(self):
        c,m=self.candidate()
        def predict(im,points,box,prior):
            np.testing.assert_array_equal(prior['mask'],m)
            return dict(mask=m,score=.9,logits=np.ones((1,256,256),np.float32),context={'test':True},prior_source='binary_mask_seed')
        with patch.object(self.api.model,'prompt',side_effect=predict):r=self.post('sam/prompt',{'image_id':self.id,'parent':c['id'],'mode':'edit','points':[[30,25,1]]})
        from tem_analyzer.v2_api import load_prior
        prior=load_prior(self.api.project,self.id,r);self.assertEqual(prior['logits'].shape,(1,256,256));self.assertTrue(self.api.project.state['runs'][-1]['seconds']>=0);self.assertIn('image_sha256',self.api.project.state['runs'][-1])
    def test_batch_ocr_missing_weights_uses_explicit_common_fallback(self):
        self.api.project.state['legacy_templates_enabled']=True
        im=np.full((60,80,3),40,np.uint8);im[40:43,10:50]=240;buf=io.BytesIO();Image.fromarray(im).save(buf,format='PNG')
        iid=self.client.post('/api/images',files={'file':('bar.png',buf.getvalue(),'image/png')}).json()['image_id']
        self.post('preprocessing/apply',{'template':{'id':'ocr','name':'ocr','scale_roi':[0,.5,1,.9],'scale_text_roi':[0,.2,1,.5],'text_rois':[]},'image_ids':[iid],'apply_regions':True,'apply_scale':False})
        with patch('tem_analyzer.ocr.read_words',side_effect=ValueError('no offline weights')):
            r=self.post('v2/ocr-batch',{'image_ids':[iid],'fallback_length':50,'unit':'nm'})
        self.assertEqual(r[iid]['nm_per_px'],1.25);self.assertFalse(r[iid]['confirmed']);self.assertEqual(r[iid]['source'],'manual-common-fallback');self.assertIn('ocr_warning',r[iid])
    def test_migrate_v1_creates_backup(self):
        p=self.api.project;s=p.state.copy();s['schema_version']=1;p.path.write_text(json.dumps(s));q=Project(self.temp.name);self.assertEqual(q.state['schema_version'],2);self.assertEqual(len(list(q.root.glob('project.v1.backup.*.json'))),1)
    def test_original_resolution_boundary_and_topology_guard(self):
        yy,xx=np.mgrid[:96,:128];m=(xx-64)**2+(yy-48)**2<25**2
        im=np.repeat(np.where((xx-64)**2+(yy-48)**2<28**2,40,210)[...,None],3,axis=2).astype('uint8')
        r=refine_all(im,m,np.ones(m.shape,bool),{'inside':6,'outside':6,'polarity':'positive'})
        self.assertEqual(r['mask'].shape,m.shape);self.assertEqual(topology(r['mask']),topology(m));self.assertGreater(r['mask'].sum(),m.sum());self.assertTrue(r['loops'][0]['peak']);self.assertEqual(len(r['loops'][0]['response']),len(r['loops'][0]['initial']))

if __name__=='__main__':unittest.main()
