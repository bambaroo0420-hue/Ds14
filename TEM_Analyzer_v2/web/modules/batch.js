export function mountBatch(T,metrology) {
  const $=id=>document.getElementById(id);let lastId=null,timer=null;
  function ids(){return $('batchScope').value==='all'?Object.keys(T.state.images):T.selectedImages.length?T.selectedImages:[T.current].filter(Boolean)}
  function settings(){return {ocr_dir:$('ocrDir').value,enhanced_ocr:$('enhancedOCR').checked,apply_annotations:$('autoApplyAnnotations').checked,
    reference_image:$('referenceImage').value,match_threshold:+$('matchThreshold').value,
    sam:{grid:+$('grid').value,pred_iou:+$('pred').value,stability:+$('stability').value,nms:+$('nms').value,prompt_source:$('batchPromptSource').value,features:T.featurePromptConfig()},
    boundary:{radius:+$('layerRadius').value,max_gap:+$('layerGap').value},
    scope_id:T.scopeId(),rotation:metrology.rotationConfig(),measurement:metrology.measurementConfig()}}
  async function poll(){
    clearTimeout(timer);
    try{
      const jobs=await T.api('workflow/jobs',null,'GET'),job=jobs.at(-1);
      if(job){
        lastId=job.id;$('jobProgress').value=job.done;$('jobProgress').max=job.total;
        const counts=status=>job.rows.filter(r=>r.status===status).length;
        $('jobInfo').textContent=`${job.status} · 처리 ${job.done}/${job.total} (성공 ${counts('done')}, 실패 ${counts('failed')}, 건너뜀 ${counts('skipped')}) · ${job.active_stage||''}`;
        $('jobRows').textContent=job.rows.map(r=>`${T.state.images[r.image_id]?.name||r.image_id} · ${r.stage} · ${r.status}${r.error?' · '+r.error:''}${r.stage==='rotation'&&r.result?` · ${r.result.angle_deg.toFixed(4)}° · 잔차 ${r.result.residual_px==null?'해당 없음':r.result.residual_px.toFixed(2)+'px'} · 미확정 · ${(r.result.warnings||[]).join(' ')}`:''}`).join('\n');
        const running=['queued','running','cancelling'].includes(job.status);
        $('cancelJob').disabled=!running;$('startJob').disabled=running;
        if(running){timer=setTimeout(poll,800);return}
        if($('jobInfo').dataset.running==='true'){$('jobInfo').dataset.running='false';await T.refresh()}
      }
    }catch(e){T.say(e.message);timer=setTimeout(poll,1500)}
  }
  $('startJob').onclick=()=>T.task(async()=>{
    const steps=[...document.querySelectorAll('[data-job-step]:checked')].map(x=>x.dataset.jobStep);
    await T.api('workflow/jobs/start',{image_ids:ids(),steps,settings:settings()});$('jobInfo').dataset.running='true';setTimeout(poll,0);
  });
  window.addEventListener('tem:job-started',()=>{$('jobInfo').dataset.running='true';poll()});
  $('cancelJob').onclick=async()=>{try{await T.api('workflow/jobs/cancel',{});await poll()}catch(e){T.say(e.message)}};
  $('retryJob').onclick=()=>T.task(async()=>{await T.api('workflow/jobs/retry',{job_id:lastId});$('jobInfo').dataset.running='true';setTimeout(poll,0)});
  for(const [id,kind] of [['confirmSelectedScales','scale'],['confirmSelectedRotations','rotation']]){
    $(id).onclick=()=>T.task(async()=>{await T.api('workflow/confirm-many',{image_ids:ids(),kind});await T.refresh()});
  }
  $('exportBatch').onclick=()=>T.task(async()=>{const r=await T.api('workflow/export',{image_ids:ids(),...T.exportOptions()});T.download(await r.blob(),'TEM_batch_results.zip')});
  poll();return {poll};
}
