import copy
from test_workflow import WorkflowTest
from tem_analyzer.services.layers import fingerprint


class ScaleReviewTests(WorkflowTest):
    def proposal(self):
        p=self.api.project
        p.state['annotation_proposals'][self.id]={'input_hash':fingerprint(p,self.id),'scale':{'nm_per_px':.05,'confirmed':False},'template':{'text_rois':[[0,0,.1,.1]]}}
        p.save()

    def test_detect_only_review_save_confirm_and_restart(self):
        self.proposal();p=self.api.project;before=copy.deepcopy(p.state);disk=p.path.read_bytes()
        payload={'image_ids':[self.id]}
        r=self.client.post('/api/workflow/scales/review',json=payload)
        self.assertEqual(r.status_code,200);row=r.json()['rows'][0]
        self.assertTrue(row['can_apply']);self.assertFalse(row['ready']);self.assertIn('미적용',row['status'])
        self.assertEqual(p.state,before);self.assertEqual(p.path.read_bytes(),disk)
        r=self.client.post('/api/workflow/confirm-many',json={**payload,'kind':'scale'})
        self.assertEqual(r.status_code,400);self.assertIn('미적용',r.json()['detail'])
        exclusions=copy.deepcopy(p.state['preprocessing'][self.id])
        r=self.client.post('/api/workflow/scales/apply-proposals',json=payload)
        self.assertEqual(r.status_code,200);self.assertFalse(r.json()['exclusion_regions_changed'])
        self.assertEqual(p.state['preprocessing'][self.id]['template'],exclusions['template'])
        self.assertFalse(p.state['scale'][self.id]['confirmed'])
        r=self.client.post('/api/workflow/confirm-many',json={**payload,'kind':'scale'})
        self.assertEqual(r.status_code,200);self.assertTrue(p.state['scale'][self.id]['confirmed'])
        from tem_analyzer.storage import Project
        self.assertTrue(Project(p.root).state['scale'][self.id]['confirmed'])

    def test_stale_and_existing_calibration_are_not_overwritten(self):
        self.proposal();p=self.api.project
        p.state['annotation_proposals'][self.id]['input_hash']='stale'
        r=self.client.post('/api/workflow/scales/apply-proposals',json={'image_ids':[self.id]})
        self.assertEqual(r.status_code,400);self.assertNotIn(self.id,p.state['scale'])
        self.proposal();p.state['scale'][self.id]={'nm_per_px':2,'confirmed':True};p.save()
        r=self.client.post('/api/workflow/scales/apply-proposals',json={'image_ids':[self.id]})
        self.assertEqual(r.status_code,400);self.assertEqual(p.state['scale'][self.id]['nm_per_px'],2)

    def test_invalid_selected_id_cannot_partially_apply(self):
        self.proposal();p=self.api.project
        r=self.client.post('/api/workflow/scales/apply-proposals',json={'image_ids':[self.id,'missing']})
        self.assertEqual(r.status_code,400);self.assertNotIn(self.id,p.state['scale'])
