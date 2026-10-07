import copy,unittest
from unittest.mock import patch,Mock
import numpy as np
import test_workflow
from tem_analyzer.roi_domains import crop_guard,candidate_domains,crop_contacts
from tem_analyzer.sam_service import ModelService
from tem_analyzer.services.scopes import scope_arrays
from tem_analyzer.labels import compose,UNKNOWN,pack


class IndependentROITests(unittest.TestCase):
    setUp=test_workflow.WorkflowTest.setUp
    tearDown=test_workflow.WorkflowTest.tearDown

    def post(self,route,body):
        r=self.client.post('/api/'+route,json=body);self.assertEqual(r.status_code,200,r.text);return r.json()

    def item(self):
        m=np.zeros((60,80),bool);m[20:30,20:60]=True
        return dict(mask=m,score=.9,inference_domains=[[20,10,60,50]],mask_choice=1,multimask_scores=[.8,.9,.6],prompt_violations=[1])

    def preview(self):
        with patch.object(self.api.model,'in_roi',return_value=self.item()) as model:
            r=self.post('sam/prompt',dict(image_id=self.id,roi=[20,10,60,50],points=[[40,25,1]],preview=True,mask_choice=1))
            self.assertEqual(model.call_args.kwargs['mask_choice'],1)
        return r

    def test_independent_preview_cancel_accept_provenance_no_parent(self):
        p=self.api.project;before=copy.deepcopy(p.state);r=self.preview()
        self.assertTrue(r['crop_truncated']);self.assertEqual(r['prompt_violations'],[1]);self.assertEqual(p.state,before)
        self.assertFalse(list((p.root/'masks').glob('*.png')))
        self.client.delete('/api/roi-previews/'+r['preview_token']);self.assertFalse(p.state['candidates'][self.id])
        r=self.preview();c=self.post('roi-previews/'+r['preview_token']+'/accept',{})
        self.assertIsNone(c['parent']);self.assertIsNone(c['layer_id']);self.assertEqual(c['source'],'roi-extract')
        self.assertEqual(c['inference_domains'],[[20,10,60,50]]);self.assertEqual(c['mask_choice'],1)
        self.assertEqual(self.client.post('/api/roi-previews/'+r['preview_token']+'/accept',json={}).status_code,410)

    def test_independent_preview_exclusion_staleness_and_excluded_prompt(self):
        r=self.preview();ex=np.zeros((60,80),bool);ex[20:30,35:45]=True
        self.api.project.state['annotations'][self.id]={'exclude':pack(ex)}
        self.assertEqual(self.client.post('/api/roi-previews/'+r['preview_token']+'/accept',json={}).status_code,409)
        with patch.object(self.api.model,'in_roi') as infer:
            response=self.client.post('/api/sam/prompt',json=dict(image_id=self.id,roi=[20,10,60,50],points=[[40,25,1]],preview=True))
            self.assertEqual(response.status_code,400);infer.assert_not_called()

    def test_crop_cut_unknown_gt_valid_thickness_but_invalid_cd_and_inheritance(self):
        p=self.api.project;r=self.preview();c=self.post('roi-previews/'+r['preview_token']+'/accept',{})
        self.post('workflow/scopes/save',dict(image_id=self.id,candidate_ids=[c['id']]))
        mask,labels,valid,items=scope_arrays(p,self.id,'target');self.assertEqual(labels[25,20],UNKNOWN);self.assertTrue(valid[25,40])
        self.assertTrue(crop_guard(p,self.id,items)[25,20]);self.assertFalse(crop_guard(p,self.id,items)[25,40])
        self.post('workflow/rotation/preview',dict(image_id=self.id,config=dict(scope_id='target',mode='edge')))
        self.post('workflow/rotation/confirm',dict(image_id=self.id));self.post('scale/manual',dict(image_id=self.id,a=[5,5],b=[55,5],length=50))
        thick=self.post('workflow/measurement',dict(image_id=self.id,config=dict(scope_id='target',axis='thickness',start=40,stop=40,step=1)))
        self.assertEqual(thick['summary']['mean'],10)
        cd=self.post('workflow/measurement',dict(image_id=self.id,config=dict(scope_id='target',axis='cd',start=25,stop=25,step=1)))
        self.assertEqual(cd['summary']['count'],0);self.assertEqual(cd['rows'][0]['status'],'invalid_region');self.assertEqual(cd['rows'][0]['raw_length_nm'],40)
        duplicate=self.post('candidates/duplicate',dict(image_id=self.id,candidate_id=c['id']))
        self.assertEqual(duplicate['inference_domains'],c['inference_domains'])
        brushed=self.post('candidates/brush',dict(image_id=self.id,candidate_id=c['id'],strokes=[]))
        self.assertEqual(brushed['inference_domains'],c['inference_domains'])
        p.candidate(self.id,c['id']).update(layer_id=1,reviewed=True)
        lab,v,_=compose(p,self.id,True);self.assertEqual(lab[25,20],UNKNOWN);self.assertTrue(v[25,40])

    def test_all_crop_edges_cannot_be_perfect_zero_rotation(self):
        p=self.api.project;m=np.zeros((60,80),bool);m[10:50,20:60]=True
        c=p.put_candidate(self.id,m,'roi-extract',inference_domains=[[20,10,60,50]])
        self.post('workflow/scopes/save',dict(image_id=self.id,candidate_ids=[c['id']]))
        r=self.client.post('/api/workflow/rotation/preview',json=dict(image_id=self.id,config=dict(scope_id='target',mode='auto')))
        self.assertEqual(r.status_code,400)

    def test_near_crop_endpoint_guard_and_true_frame_distinction(self):
        m=np.zeros((60,80),bool);m[25:28,22:58]=True
        contacts=crop_contacts(m,[[20,10,60,50]])
        self.assertTrue(contacts[25,22]);self.assertTrue(contacts[25,57]);self.assertFalse(contacts[25,25])
        self.assertFalse(crop_contacts(np.ones((60,80),bool),[[0,0,80,60]]).any())

    def test_roi_edit_preserves_parent_outside_without_new_cut_domain(self):
        p=self.api.project;old=np.ones((60,80),bool);c=p.put_candidate(self.id,old,'full-parent')
        with patch.object(self.api.model,'in_roi',return_value=self.item()):
            r=self.post('sam/prompt',dict(image_id=self.id,parent=c['id'],mode='edit',roi=[20,10,60,50],points=[[40,25,1]],preview=True))
        saved=self.post('roi-previews/'+r['preview_token']+'/accept',{})
        self.assertEqual(candidate_domains(saved),[]);self.assertTrue(p.mask(self.id,saved['id'])[0,0])

    def test_native_selector_and_roi_coordinates(self):
        service=ModelService();im=np.zeros((60,80,3),np.uint8)
        def infer(image,points,box,**kwargs):
            self.assertEqual(image.shape,(40,40,3));self.assertEqual(points,[[10,15,1]])
            self.assertEqual(box,[2,2,30,30]);self.assertEqual(kwargs['mask_choice'],2)
            return dict(mask=np.ones((40,40),bool),score=.9,logits=np.zeros((1,256,256)),context={})
        with patch.object(service,'prompt',side_effect=infer):
            value=service.in_roi(im,[20,10,60,50],[[30,25,1]],[22,12,50,40],mask_choice=2)
        self.assertTrue(value['mask'][10:50,20:60].all());self.assertFalse(value['mask'][:10].any());self.assertNotIn('logits',value)
        for roi,box in [([20.1,10,60,50],None),([20,10,60,50],[1,2])]:
            with self.assertRaises(ValueError):service.in_roi(im,roi,[[30,25,1]],box)

    def test_native_multimask_selection_adherence_and_single_mask_rejection(self):
        service=ModelService();service.model=object();service.info={'checkpoint_sha256':'test'}
        service.predictor=Mock();im=np.zeros((10,12,3),np.uint8)
        logits=np.full((3,10,12),-10.,np.float32);logits[0,2,3]=10;logits[1,:,:]=10
        service.predictor.predict.return_value=(logits,np.array([.8,.99,.1]),np.zeros((3,256,256)))
        chosen=service.prompt(im,[[3,2,1],[5,5,0]],mask_choice=0)
        self.assertEqual(chosen['mask_choice'],0);self.assertEqual(chosen['prompt_violations'],[])
        auto=service.prompt(im,[[3,2,1],[5,5,0]])
        self.assertEqual(auto['mask_choice'],1);self.assertEqual(auto['prompt_violations'],[1]);self.assertTrue(auto['embedding_reused'])
        self.assertEqual(service.predictor.set_image.call_count,1)
        service.info['single_mask']=True;service.predictor.predict.return_value=(logits[:1],np.array([.8]),np.zeros((1,256,256)))
        with self.assertRaises(ValueError):service.prompt(im,[[3,2,1]],mask_choice=2)
        self.assertFalse(service.predictor.predict.call_args.kwargs['multimask_output'])


if __name__=='__main__':unittest.main()
