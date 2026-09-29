"""One worker per project. Each image/stage commits atomically; cancel between stages."""
import asyncio
import copy
import time
import uuid


class JobManager:
    def __init__(self,project,gate,execute):
        self.project=project;self.gate=gate;self.execute=execute;self.task=None;self.current=None
        # In-flight work cannot silently appear completed after restart.
        for job in project.state.setdefault('jobs',[]):
            if job['status'] in ('running','queued','cancelling'):job['status']='interrupted'
        project.save()

    def start(self,ids,steps,settings):
        if self.task and not self.task.done():raise ValueError('이미 일괄 작업이 실행 중입니다.')
        ids=list(dict.fromkeys(ids))
        if not ids or not steps:raise ValueError('이미지와 처리 단계를 선택하세요.')
        for iid in ids:self.project.require_image(iid)
        allowed={'annotations','sam','match','boundary','rotation','measurement','gt'}
        if any(s not in allowed for s in steps):raise ValueError('지원하지 않는 일괄 단계')
        steps=list(dict.fromkeys(steps))
        order=['annotations','sam','match','boundary','gt','rotation','measurement']
        steps=sorted(steps,key=order.index)
        self.current=dict(id=uuid.uuid4().hex,status='queued',image_ids=ids,steps=steps,settings=copy.deepcopy(settings),
                          rows=[],done=0,total=len(ids)*len(steps),started=time.time(),cancel_requested=False)
        self.project.state['jobs']=self.project.state['jobs'][-19:]+[self.current]
        self.project.busy_job=True;self.project.save()
        self.task=asyncio.create_task(self.run())
        return copy.deepcopy(self.current)

    def cancel(self):
        if self.current and self.current['status'] in ('running','queued','cancelling'):
            self.current.update(cancel_requested=True,status='cancelling')
        return copy.deepcopy(self.current)

    async def run(self):
        job=self.current;job['status']='running'
        try:
            for iid in job['image_ids']:
                for stage in job['steps']:
                    if job['cancel_requested']:break
                    job['active_image']=iid;job['active_stage']=stage
                    async with self.gate:
                        before=copy.deepcopy(self.project.state)
                        try:
                            self.project.checkpoint('batch:'+stage+':'+iid)
                            result=await asyncio.to_thread(self.execute,iid,stage,job['settings'])
                            job['rows'].append(dict(image_id=iid,stage=stage,status='done',result=result))
                        except Exception as exc:
                            # Candidate files are immutable and can safely be orphaned on rollback.
                            self.project.state=before
                            self.project.state['jobs'][-1]=job
                            job['rows'].append(dict(image_id=iid,stage=stage,status='failed',error=str(exc)))
                            job['done']+=1;self.project.save();break
                        job['done']+=1;self.project.save()
                    await asyncio.sleep(0)
                if job['cancel_requested']:break
            job['status']='cancelled' if job['cancel_requested'] else ('completed_with_errors' if any(r['status']=='failed' for r in job['rows']) else 'completed')
        except asyncio.CancelledError:
            job['status']='interrupted'
            raise
        finally:
            job['finished']=time.time();self.project.busy_job=False;self.project.save()
