import io
import json
import os
import threading
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from test_workflow import WorkflowTest
from tem_analyzer import storage


class RecoveryTests(WorkflowTest):
    def predictions(self):
        out=[]
        for y in (5,20,35):
            m=np.zeros((60,80),bool);m[y:y+10,10:60]=True
            out.append(dict(mask=m,score=.99,stability=.99))
        return out

    def run_sam(self):
        with patch.object(self.api.model,'automatic',return_value=self.predictions()):
            return self.client.post('/api/sam/prepared',json={'image_id':self.id,'auto_points':[[20,20]]})

    def test_prepared_sam_commits_metadata_once_and_restarts(self):
        with patch.object(storage,'atomic_json',wraps=storage.atomic_json) as writes:
            r=self.run_sam()
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['count'],3)
        self.assertEqual(writes.call_count,1)
        restored=storage.Project(self.api.project.root)
        self.assertEqual(len(restored.state['candidates'][self.id]),3)
        self.assertEqual(len(restored.state['runs']),1)

    def test_partial_mask_failure_keeps_metadata_and_blocks_edits(self):
        p=self.api.project;before=p.path.read_bytes();original=p.put_candidate;calls=[]
        def fail(*args,**kwargs):
            calls.append(1)
            if len(calls)==2:raise OSError('controlled mask write failure')
            return original(*args,**kwargs)
        with patch.object(p,'put_candidate',side_effect=fail):r=self.run_sam()
        self.assertEqual(r.status_code,503,r.text);self.assertEqual(p.path.read_bytes(),before)
        self.assertEqual(p.state['candidates'][self.id],[]);self.assertFalse(p._defer_saves)
        self.assertEqual(self.client.post('/api/layers',json={'name':'blocked'}).status_code,503)
        self.assertEqual(self.client.post('/api/workflow/jobs/start',json={}).status_code,503)
        self.assertTrue(self.client.get('/api/state').json()['storage_error'])
        with self.assertRaises(OSError):p.save()

    def test_final_commit_failure_preserves_disk(self):
        p=self.api.project;before=p.path.read_bytes()
        with patch.object(storage,'atomic_json',side_effect=OSError('controlled commit failure')):r=self.run_sam()
        self.assertEqual(r.status_code,503);self.assertEqual(p.path.read_bytes(),before)
        self.assertEqual(p.state['candidates'][self.id],[])

    def test_model_error_and_invalid_prompt_do_not_lock_storage(self):
        before=self.api.project.path.read_bytes()
        with patch.object(self.api.model,'automatic',side_effect=RuntimeError('model failed')):
            r=self.client.post('/api/sam/prepared',json={'image_id':self.id,'auto_points':[[20,20]]})
        self.assertEqual(r.status_code,400);self.assertEqual(self.api.project.path.read_bytes(),before)
        self.assertFalse(getattr(self.api.project,'_storage_error',None));self.assertFalse(self.api.project._defer_saves)
        self.assertEqual(self.client.post('/api/sam/prepared',json={'image_id':self.id}).status_code,400)
        self.assertEqual(self.run_sam().status_code,200)

    def test_bad_image_is_read_error_not_project_lock(self):
        r=self.client.post('/api/images',files={'file':('bad.png',b'not an image','image/png')})
        self.assertEqual(r.status_code,400,r.text);self.assertIn('이미지 읽기 실패',r.json()['detail'])
        self.assertFalse(getattr(self.api.project,'_storage_error',None))
        self.assertEqual(self.run_sam().status_code,200)

    def test_large_multipart_read_and_image_reload(self):
        image=np.random.default_rng(23).integers(0,256,(800,1000,3),dtype=np.uint8)
        b=io.BytesIO();Image.fromarray(image).save(b,format='PNG')
        self.assertGreater(len(b.getvalue()),1024*1024)
        r=self.client.post('/api/images',files={'file':('large.png',b.getvalue(),'image/png')})
        self.assertEqual(r.status_code,200,r.text);iid=r.json()['image_id']
        r=self.client.get(f'/api/images/{iid}.png');self.assertEqual(r.status_code,200)
        np.testing.assert_array_equal(np.asarray(Image.open(io.BytesIO(r.content))),image)
        self.assertEqual(self.client.get(f'/api/thumbnails/{iid}.jpg').status_code,200)

    def test_upload_temporary_read_error_has_specific_message(self):
        from starlette.datastructures import UploadFile
        with patch.object(UploadFile,'read',side_effect=OSError('controlled temp read error')):
            r=self.client.post('/api/images',files={'file':('test.png',b'test','image/png')})
        self.assertEqual(r.status_code,503,r.text);self.assertIn('임시 파일 읽기 실패',r.json()['detail'])
        self.assertFalse(getattr(self.api.project,'_storage_error',None))

    def test_upload_metadata_failure_rolls_back_memory(self):
        p=self.api.project;before=p.path.read_bytes();ids=set(p.state['images'])
        b=io.BytesIO();Image.new('RGB',(12,12)).save(b,format='PNG')
        with patch.object(storage,'atomic_json',side_effect=OSError('controlled metadata failure')):
            r=self.client.post('/api/images',files={'file':('test.png',b.getvalue(),'image/png')})
        self.assertEqual(r.status_code,503);self.assertEqual(set(p.state['images']),ids)
        self.assertEqual(p.path.read_bytes(),before)

    def test_primary_error_not_masked_and_retry_is_bounded(self):
        p=self.api.project;before=p.path.read_bytes()
        primary=PermissionError('PRIMARY');primary.winerror=5
        secondary=PermissionError('SECONDARY');secondary.winerror=32
        with patch.object(storage.os,'replace',side_effect=primary) as replace,patch.object(storage.os,'unlink',side_effect=secondary),patch.object(storage.time,'sleep') as sleep,self.assertLogs('tem_analyzer.storage',level='WARNING'):
            with self.assertRaises(PermissionError) as caught:p.save()
        self.assertIs(caught.exception,primary);self.assertEqual(replace.call_count,8)
        self.assertAlmostEqual(sum(c.args[0] for c in sleep.call_args_list),5.6)
        self.assertEqual(p.path.read_bytes(),before)

    @unittest.skipUnless(os.name=='nt','Windows sharing lock test')
    def test_real_transient_windows_lock(self):
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE;kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        original=os.replace;calls=[];timers=[]
        def delayed(src,dst):
            calls.append(1)
            if len(calls)==1:
                handle=kernel.CreateFileW(str(src),0x80000000,3,None,3,0,None)
                if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
                timer=threading.Timer(.1,lambda:kernel.CloseHandle(handle));timer.start();timers.append(timer)
            return original(src,dst)
        try:
            with patch.object(os,'replace',side_effect=delayed):r=self.run_sam()
        finally:
            for timer in timers:timer.join()
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(len(calls),2)


if __name__=='__main__':unittest.main()
