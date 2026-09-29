import io
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from test_workflow import WorkflowTest

class PromptTests(WorkflowTest):
    def test_preparation_does_not_infer_and_selected_points_are_executed(self):
        c=self.client
        with patch.object(self.api.model,'automatic',side_effect=AssertionError('SAM must not run')):
            g=c.post('/api/prompts/grid',json={'image_id':self.id,'grid':4})
            self.assertEqual(g.status_code,200,g.text)
            self.assertFalse(g.json()['inference_run'])
            m=c.post('/api/prompts/ml',json={'image_id':self.id,'existing':g.json()['points'],'count':3})
            self.assertEqual(m.status_code,200,m.text)
            self.assertFalse(m.json()['inference_run'])
        dots=g.json()['points'][:-1]
        mask=np.zeros((60,80),bool);mask[10:20,10:20]=1
        with patch.object(self.api.model,'automatic',return_value=[{'mask':mask,'score':.9,'stability':.99}]) as auto:
            r=c.post('/api/sam/prepared',json={'image_id':self.id,'auto_points':dots})
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(auto.call_args.kwargs['prepared_points'],dots)
        self.assertEqual(c.post('/api/sam/prepared',json={'image_id':self.id}).status_code,400)

    def test_layer_union_and_deletion(self):
        p=self.api.project;c=self.client
        masks=[]
        for x in (10,40):
            mask=np.zeros((60,80),bool);mask[10:20,x:x+10]=1;masks.append(mask)
            item=p.put_candidate(self.id,mask,'test')
            c.post('/api/layers/assign',json={'image_id':self.id,'candidate_id':item['id'],'layer_id':1})
        r=c.get(f'/api/layer-mask/{self.id}/1.png')
        actual=np.asarray(Image.open(io.BytesIO(r.content)))>0
        np.testing.assert_array_equal(actual,masks[0]|masks[1])
        r=c.delete('/api/layers/1');self.assertEqual(r.status_code,200)
        self.assertEqual(len(p.state['candidates'][self.id]),2)
        self.assertTrue(all(x['layer_id'] is None for x in p.state['candidates'][self.id]))
        item=p.state['candidates'][self.id][0]
        self.assertEqual(c.delete(f'/api/candidates/{self.id}/{item["id"]}').status_code,200)
        self.assertTrue(p.mask_path(self.id,item['id']).exists())  # immutable mask retained for undo
        self.assertIsNone(p.candidate(self.id,item['id']))
        self.assertEqual(c.post('/api/layers',json={'name':'다시 추가'}).status_code,200)

    def test_ml_proposals_are_in_bounds_and_away_from_existing(self):
        from tem_analyzer.prompts import ml_points
        im=np.zeros((90,120,3),np.uint8);im[:30]=60;im[30:60]=160;im[60:]=240
        ex=np.zeros((90,120),bool);ex[:,:8]=True
        dots=ml_points(im,ex,[[60,45]],count=5,clusters=3,min_distance=10)
        self.assertGreater(len(dots),0)
        for x,y in dots:
            self.assertFalse(ex[int(y),int(x)])
            self.assertGreaterEqual(np.hypot(x-60,y-45),10)

if __name__=='__main__':unittest.main()

