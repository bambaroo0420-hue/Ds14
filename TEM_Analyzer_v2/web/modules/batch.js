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
  $('confirmSelectedScales').onclick=()=>T.task(async()=>{
    const image_ids=ids();if(!image_ids.length)throw Error('이미지를 선택하세요.');
    const dialog=document.createElement('dialog');dialog.id='scaleReviewDialog';
    dialog.innerHTML='<h2>대상 이미지 스케일 검토</h2><p>단위는 nm/px입니다. 검출만 실행한 값은 아직 저장되지 않습니다. 바 위치·길이는 1 이미지·스케일에서 확인하세요.</p><table><thead><tr><th>이미지</th><th>저장값</th><th>검출 제안</th><th>상태</th></tr></thead><tbody></tbody></table><p data-error></p><button data-apply>미적용 검출값만 저장 (제외 박스는 변경 안 함)</button><button data-confirm>저장된 스케일 확인 후 확정</button><button data-close>닫기</button>';
    let rows=[];
    async function render(){rows=(await T.api('workflow/scales/review',{image_ids})).rows;const tbody=dialog.querySelector('tbody');tbody.replaceChildren();for(const row of rows){const tr=document.createElement('tr');for(const value of [row.name,row.saved??'—',row.detected??'—',row.status]){const td=document.createElement('td');td.textContent=String(value);tr.append(td)}tbody.append(tr)}dialog.querySelector('[data-apply]').disabled=!rows.some(r=>r.can_apply);dialog.querySelector('[data-confirm]').disabled=!rows.length||rows.some(r=>!r.ready)}
    async function action(fn){const controls=[...dialog.querySelectorAll('button')];controls.forEach(b=>b.disabled=true);try{await fn();await T.refresh();dialog.querySelector('[data-error]').textContent=''}catch(e){dialog.querySelector('[data-error]').textContent=e.message}finally{try{await render()}catch(e){dialog.querySelector('[data-error]').textContent=e.message}dialog.querySelector('[data-close]').disabled=false}}
    dialog.querySelector('[data-apply]').onclick=()=>action(()=>T.api('workflow/scales/apply-proposals',{image_ids:rows.filter(r=>r.can_apply).map(r=>r.image_id)}));
    dialog.querySelector('[data-confirm]').onclick=()=>action(()=>T.api('workflow/confirm-many',{image_ids,kind:'scale'}));
    dialog.querySelector('[data-close]').onclick=()=>dialog.close();dialog.addEventListener('close',()=>dialog.remove());
    await render();document.body.append(dialog);dialog.showModal();
  });
  for(const [id,kind] of [['confirmSelectedRotations','rotation']]){
    $(id).onclick=()=>T.task(async()=>{await T.api('workflow/confirm-many',{image_ids:ids(),kind});await T.refresh()});
  }
  $('exportBatch').onclick=()=>T.task(async()=>{const r=await T.api('workflow/export',{image_ids:ids(),...T.exportOptions()});T.download(await r.blob(),'TEM_batch_results.zip')});
  poll();return {poll};
}
