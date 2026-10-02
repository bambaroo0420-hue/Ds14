import asyncio
import copy
import io
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from tem_analyzer.storage import Project
from tem_analyzer.jobs.manager import JobManager
from tem_analyzer.services.prompt_transfer import save_preset
from tem_analyzer.services.prompt_batches import prepare_transfer,current_transfer,confirm_transfers,transfer_signature
from test_workflow import WorkflowTest


class TransferTests(WorkflowTest):
    def prepare(self):
        draft=dict(auto_points=[[20,20]],manual_points=[[30,30,1],[50,40,0]],box=[10,10,65,50],manual_mode='object')
        save_preset(self.api.project,self.id,'reuse',draft)
        return prepare_transfer(self.api.project,self.id,'reuse','normalized')

    def confirm(self,value=None):
        value=value or current_transfer(self.api.project,self.id)
        confirm_transfers(self.api.project,[dict(image_id=self.id,signature=transfer_signature(value))])

    def test_prepare_and_preview_never_run_sam(self):
        with patch.object(self.api.model,'automatic',side_effect=AssertionError('unexpected SAM')):
            value=self.prepare()
            self.assertFalse(value['inference_run']);self.assertFalse(self.api.project.state['candidates'][self.id])
            response=self.client.get(f'/api/workflow/prompt-transfers/{self.id}')
            self.assertEqual(response.status_code,200,response.text);self.assertFalse(response.json()['reviewed'])
            response=self.client.get(f'/api/workflow/prompt-transfers/{self.id}/preview.png')
            self.assertEqual(response.status_code,200,response.text);self.assertEqual(Image.open(io.BytesIO(response.content)).size,(80,60))

    def test_review_stale_signature_and_preset_change(self):
        self.prepare()
        r=self.client.post('/api/workflow/prompt-transfers/confirm',json={'entries':[{'image_id':self.id,'signature':'stale'}]})
        self.assertEqual(r.status_code,400);self.assertIsNone(current_transfer(self.api.project,self.id)['review_hash'])
        self.confirm();current_transfer(self.api.project,self.id,True)
        self.api.project.state['prompt_presets']['reuse']['draft']['auto_points'][0]=[25,25]
        with self.assertRaisesRegex(ValueError,'preset'):current_transfer(self.api.project,self.id,True)

    def test_filter_exclusion_and_draft_edits_expire_review(self):
        self.prepare();self.confirm()
        self.api.project.state['preprocessing'][self.id]['sam_filter']={'enabled':True,'method':'median'}
        with self.assertRaises(ValueError):current_transfer(self.api.project,self.id,True)
        self.prepare();self.confirm()
        self.api.project.state['preprocessing'][self.id]['auto_regions']={'text_rois':[[0,0,.1,.1]],'scale_roi':None}
        with self.assertRaises(ValueError):current_transfer(self.api.project,self.id,True)
        self.prepare();self.confirm();self.api.project.state['prompt_transfers'][self.id]['draft']['auto_points'][0]=[27,25]
        with self.assertRaises(ValueError):current_transfer(self.api.project,self.id,True)

    def test_unreviewed_blocks_sam_then_mixed_prompts_preserve_old_candidates(self):
        self.prepare();mask=np.zeros((60,80),bool);mask[20:40,20:60]=1
        old=self.api.project.put_candidate(self.id,mask,'existing');old_before=copy.deepcopy(old)
        settings={'sam':{'prompt_source':'transferred','grid':16}}
        item=dict(mask=mask,score=.9,stability=.99)
        with patch.object(self.api.model,'automatic',return_value=[item]) as auto,patch.object(self.api.model,'prompt',return_value=item) as manual:
            with self.assertRaises(ValueError):self.api.app.state.workflow_jobs.execute(self.id,'sam',settings)
            auto.assert_not_called();manual.assert_not_called()
            self.confirm();r=self.api.app.state.workflow_jobs.execute(self.id,'sam',settings)
            self.assertEqual(r['count'],2);self.assertEqual(auto.call_args.kwargs['prepared_points'],[[20,20]])
            self.assertEqual(manual.call_args.args[1],[[30,30,1],[50,40,0]])
            self.assertEqual(manual.call_args.args[2],[10,10,65,50])
        self.assertEqual(self.api.project.candidate(self.id,old['id']),old_before)
        self.assertTrue(all(c['layer_id'] is None for c in self.api.project.state['candidates'][self.id]))
        current_transfer(self.api.project,self.id,True) # New masks do not change prompt geometry.
        self.api.project.save();current_transfer(Project(self.temp.name),self.id,True)

    def test_bulk_confirmation_is_all_or_nothing(self):
        value=self.prepare()
        with self.assertRaises(KeyError):confirm_transfers(self.api.project,[dict(image_id=self.id,signature=transfer_signature(value)),dict(image_id='missing',signature='x')])
        self.assertIsNone(value['review_hash'])

    def test_source_exclusion_change_also_expires_target_review(self):
        p=self.api.project;self.prepare();buf=io.BytesIO();Image.new('RGB',(80,60),'gray').save(buf,format='PNG')
        other=p.add_image(buf.getvalue(),'target.png')
        value=prepare_transfer(p,other,'reuse','normalized')
        confirm_transfers(p,[dict(image_id=other,signature=transfer_signature(value))])
        p.state['preprocessing'][self.id]['auto_regions']={'text_rois':[[0,0,.1,.1]],'scale_roi':None}
        with self.assertRaises(ValueError):current_transfer(p,other,True)

    def test_deleted_image_draft_recovers_with_image(self):
        p=self.api.project;self.prepare();self.confirm()
        self.client.delete('/api/images/'+self.id)
        self.assertNotIn(self.id,p.state['prompt_transfers'])
        trash=self.client.get('/api/workflow/trash').json()
        result=self.client.post('/api/workflow/trash/restore',json={'trash_id':trash[0]['id']})
        self.assertEqual(result.status_code,200,result.text);current_transfer(p,self.id,True)

    def test_independent_positive_transfer_is_not_grouped_as_one_object(self):
        save_preset(self.api.project,self.id,'reuse',dict(manual_points=[[20,20,1],[40,40,1]],manual_mode='independent'))
        prepare_transfer(self.api.project,self.id,'reuse','normalized');self.confirm()
        with patch.object(self.api.model,'automatic',return_value=[]) as auto,patch.object(self.api.model,'prompt') as manual:
            self.api.app.state.workflow_jobs.execute(self.id,'sam',{'sam':{'prompt_source':'transferred'}})
            self.assertEqual(auto.call_args.kwargs['prepared_points'],[[20,20],[40,40]]);manual.assert_not_called()


class TransferJobTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_new_preparation_never_reuses_old_review(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Project(folder);buf=io.BytesIO();Image.new('RGB',(80,60),'gray').save(buf,format='PNG')
            iid=p.add_image(buf.getvalue(),'flat.png');save_preset(p,iid,'reuse',dict(auto_points=[[20,20]]))
            value=prepare_transfer(p,iid,'reuse','normalized');confirm_transfers(p,[dict(image_id=iid,signature=transfer_signature(value))])
            def execute(iid,stage,settings):return prepare_transfer(p,iid,'reuse','ecc')
            manager=JobManager(p,asyncio.Lock(),execute)
            with self.assertRaises(ValueError):manager.start([iid],['prompt_transfer','sam'],{})
            current_transfer(p,iid,True)
            manager.start([iid],['prompt_transfer'],{});await manager.task
            self.assertEqual(manager.current['status'],'completed_with_errors')
            self.assertTrue(p.state['prompt_transfers'][iid]['superseded_by'])
            with self.assertRaisesRegex(ValueError,'이전 draft'):current_transfer(p,iid,True)
            self.assertFalse(p.state['candidates'][iid])


if __name__=='__main__':unittest.main()
