import io
import unittest
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from tem_analyzer.algorithms.gap_bridge import bridge
from tem_analyzer.services.layers import propose_boundaries,apply_boundaries,unions
from tem_analyzer.storage import Project
import test_workflow


def fixture(gap=20):
    rgb=np.full((100,120,3),40,np.uint8);rgb[50:]=190
    a=np.zeros((100,120),bool);b=a.copy();a[10:50-gap//2,10:110]=True;b[50+(gap+1)//2:90,10:110]=True
    return rgb,a,b,np.zeros_like(a)


class BridgeAlgorithmTests(unittest.TestCase):
    def test_wide_gap_common_boundary_and_no_overlap(self):
        rgb,a,b,blocked=fixture(40);r=bridge(rgb,a,b,blocked,{'max_gap':50})
        self.assertEqual(r['filled_pixels'],4000);self.assertFalse((r['mask_a']&r['mask_b']).any())
        self.assertTrue((r['mask_a']|r['mask_b'])[10:90,10:110].all())
        self.assertLessEqual(max(abs(p[1]-49.5) for t in r['traces'] for p in t['path']),1)
        self.assertFalse(((r['mask_a']|r['mask_b'])[:10]).any())

    def test_horizontal_and_swapped_layers(self):
        rgb,a,b,g=fixture();r=bridge(rgb.transpose(1,0,2),b.T,a.T,g.T,{'max_gap':30})
        self.assertEqual(r['axis'],'horizontal');self.assertEqual(r['filled_pixels'],2000)
        self.assertTrue(r['holes_preserved'])

    def test_curved_slanted_boundary_tracks_known_edge(self):
        yy,xx=np.mgrid[:140,:120]
        edge=np.rint(45+.25*xx+4*np.sin(xx/14)).astype(int)
        rgb=np.repeat(np.where(yy<edge,40,190).astype(np.uint8)[...,None],3,axis=2)
        a=(yy>=5)&(yy<edge-12)&(xx>=5)&(xx<115)
        b=(yy>=edge+12)&(yy<135)&(xx>=5)&(xx<115)
        r=bridge(rgb,a,b,np.zeros_like(a),{'max_gap':30})
        self.assertEqual(r['filled_pixels'],24*110)
        self.assertFalse((r['mask_a']&r['mask_b']).any())
        error=[abs(y-(edge[0,int(x)]-.5)) for t in r['traces'] for x,y in t['path']]
        self.assertLessEqual(max(error),1.)

    def test_width_limit_and_weak_signal_do_not_fill(self):
        rgb,a,b,g=fixture(40);self.assertEqual(bridge(rgb,a,b,g,{'max_gap':30})['filled_pixels'],0)
        rgb[:]=80;r=bridge(rgb,a,b,g,{'max_gap':50});self.assertEqual(r['filled_pixels'],0)
        self.assertGreater(r['skipped']['weak_gradient'],0)

    def test_multiple_edges_require_opt_in(self):
        rgb,a,b,g=fixture(40);rgb[42:58]=240;rgb[58:]=40
        r=bridge(rgb,a,b,g,{'max_gap':50});self.assertEqual(r['filled_pixels'],0)
        self.assertGreater(r['skipped']['multiple_edges_possible_third_layer'],0)
        r=bridge(rgb,a,b,g,{'max_gap':50,'allow_multiple_edges':True});self.assertEqual(r['filled_pixels'],4000)

    def test_hole_and_protected_pixels_preserved(self):
        rgb,a,b,g=fixture();a[20:25,20:25]=False;g[40:60,60:70]=True
        r=bridge(rgb,a,b,g,{'max_gap':30})
        self.assertFalse(r['mask_a'][20:25,20:25].any());self.assertFalse(r['changed'][g].any())
        self.assertEqual(ndi.label(ndi.binary_fill_holes(a)&~a)[1],ndi.label(ndi.binary_fill_holes(r['mask_a'])&~r['mask_a'])[1])
        self.assertGreater(r['filled_pixels'],0)

    def test_bad_parameters_and_overlap(self):
        rgb,a,b,g=fixture()
        for cfg in ({'max_gap':201},{'max_gap':1.5},{'jump':0},{'min_gradient':float('nan')},{'axis':'diagonal'}):
            with self.assertRaises(ValueError):bridge(rgb,a,b,g,cfg)
        with self.assertRaises(ValueError):bridge(rgb,a,a,g)


class BridgeAPITests(unittest.TestCase):
    setUp=test_workflow.WorkflowTest.setUp
    tearDown=test_workflow.WorkflowTest.tearDown

    def prepare(self):
        rgb,a,b,_=fixture(40);out=io.BytesIO();Image.fromarray(rgb).save(out,format='PNG')
        self.iid=self.client.post('/api/images',files={'file':('gap.png',out.getvalue(),'image/png')}).json()['image_id']
        p=self.api.project;p.state['layers']=[dict(id=1,name='A',color='#5588ee'),dict(id=2,name='B',color='#ffaa55')]
        ca=p.put_candidate(self.iid,a,'fixture');cb=p.put_candidate(self.iid,b,'fixture')
        ca.update(layer_id=1);cb.update(layer_id=2);p.save()
        return p,ca,cb,a,b

    def preview(self):
        return self.client.post('/api/workflow/boundary/preview',json=dict(image_id=self.iid,settings=dict(method='gradient_bridge',layer_a=1,layer_b=2,max_gap=50)))

    def test_preview_apply_review_gate_undo_and_reload(self):
        p,ca,cb,a,b=self.prepare();r=self.preview();self.assertEqual(r.status_code,200,r.text);r=r.json()
        np.testing.assert_array_equal(p.mask(self.iid,ca['id']),a)
        self.assertEqual(r['changed_pixels'],4000)
        self.assertEqual(self.client.get('/api/workflow/boundary/'+r['token']+'.png').status_code,200)
        self.assertEqual(self.client.post('/api/workflow/boundary/apply',json={'token':r['token']}).status_code,400)
        response=self.client.post('/api/workflow/boundary/apply',json={'token':r['token'],'confirmed_two_layers':True})
        self.assertEqual(response.status_code,200,response.text)
        m=unions(p,self.iid);self.assertFalse((m[1]&m[2]).any());self.assertEqual(int((m[1]|m[2]).sum()),8000)
        self.assertTrue(all(not c['reviewed'] for c in response.json()['created']))
        restored=Project(self.temp.name);np.testing.assert_array_equal(unions(restored,self.iid)[1],m[1])
        self.assertEqual(self.client.post('/api/v2/undo',json={}).status_code,200)
        np.testing.assert_array_equal(unions(p,self.iid)[1],a)

    def test_lock_stales_proposal_and_blocks_brush(self):
        p,ca,cb,a,b=self.prepare();r=self.preview().json()
        self.client.post('/api/v2/lock',json={'layer_id':1,'locked':True})
        self.assertEqual(self.preview().status_code,400)
        self.assertEqual(self.client.post('/api/workflow/boundary/apply',json={'token':r['token'],'confirmed_two_layers':True}).status_code,400)
        self.assertEqual(self.client.post('/api/candidates/brush',json={'image_id':self.iid,'candidate_id':ca['id'],'strokes':[]}).status_code,400)

    def test_brush_cannot_write_other_locked_layer_or_commit_stale_protection(self):
        p,ca,cb,a,b=self.prepare();self.client.post('/api/v2/lock',json={'layer_id':2,'locked':True})
        stroke=[{'mode':'add','radius':10,'points':[[55,78]]}]
        x=self.client.post('/api/candidates/brush',json={'image_id':self.iid,'candidate_id':ca['id'],'strokes':stroke}).json()
        self.assertFalse((p.mask(self.iid,x['id'])&b).any())
        stroke=[{'mode':'remove','radius':2,'points':[[20,20]]}]
        x=self.client.post('/api/candidates/brush',json={'image_id':self.iid,'candidate_id':ca['id'],'strokes':stroke}).json()
        self.client.post('/api/v2/annotations',json={'image_id':self.iid,'kind':'protect','strokes':[{'mode':'add','radius':3,'points':[[20,20]]}]})
        r=self.client.post('/api/layers/assign',json={'image_id':self.iid,'candidate_id':x['id'],'layer_id':1,'mode':'replace'})
        self.assertEqual(r.status_code,400);np.testing.assert_array_equal(p.mask(self.iid,ca['id']),a)

    def test_third_layer_and_explicit_annotation_preserved(self):
        from tem_analyzer.labels import pack
        p,ca,cb,a,b=self.prepare();third=np.zeros_like(a);third[44:56,35:45]=True
        p.state['layers'].append(dict(id=3,name='third',color='#55ddaa'))
        cc=p.put_candidate(self.iid,third,'fixture');cc['layer_id']=3
        bg=np.zeros_like(a);bg[45:55,80:90]=True;p.state['annotations'][self.iid]={'background':pack(bg)}
        result=propose_boundaries(p,self.iid,dict(method='gradient_bridge',layer_a=1,layer_b=2,max_gap=50))
        self.assertFalse((result['changed']&(third|bg)).any());np.testing.assert_array_equal(result['masks'][3],third)

    def test_nested_brush_draft_inherits_ancestor_lock(self):
        p,ca,cb,a,b=self.prepare()
        x=self.client.post('/api/candidates/brush',json={'image_id':self.iid,'candidate_id':ca['id'],'strokes':[{'mode':'remove','radius':2,'points':[[20,20]]}]}).json()
        y=self.client.post('/api/candidates/brush',json={'image_id':self.iid,'candidate_id':x['id'],'strokes':[]}).json()
        self.client.post('/api/v2/lock',json={'layer_id':1,'locked':True})
        self.assertEqual(self.client.post('/api/candidates/brush',json={'image_id':self.iid,'candidate_id':y['id'],'strokes':[]}).status_code,400)
        self.assertEqual(self.client.post('/api/layers/assign',json={'image_id':self.iid,'candidate_id':y['id'],'layer_id':2,'mode':'add'}).status_code,400)

    def test_unlock_does_not_leave_locked_pixels_permanently_protected(self):
        from tem_analyzer.labels import protection
        p,ca,cb,a,b=self.prepare();self.client.post('/api/v2/lock',json={'layer_id':2,'locked':True})
        x=self.client.post('/api/candidates/brush',json={'image_id':self.iid,'candidate_id':ca['id'],'strokes':[{'mode':'remove','radius':2,'points':[[20,20]]}]}).json()
        r=self.client.post('/api/layers/assign',json={'image_id':self.iid,'candidate_id':x['id'],'layer_id':1,'mode':'replace'})
        self.assertEqual(r.status_code,200,r.text)
        self.client.post('/api/v2/lock',json={'layer_id':2,'locked':False})
        guard=protection(p,self.iid);self.assertFalse((guard&b).any());self.assertTrue(guard[20,20])

    def test_roi_leaves_every_outside_pixel_unchanged(self):
        p,ca,cb,a,b=self.prepare()
        result=propose_boundaries(p,self.iid,dict(method='gradient_bridge',layer_a=1,layer_b=2,max_gap=50),[.3,.2,.7,.8])
        self.assertGreater(result['changed_pixels'],0)
        self.assertFalse(result['changed'][:20].any());self.assertFalse(result['changed'][80:].any())
        self.assertFalse(result['changed'][:,:36].any());self.assertFalse(result['changed'][:,84:].any())


if __name__=='__main__':unittest.main()
