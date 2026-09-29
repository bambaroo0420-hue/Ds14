/* Prepare -> inspect each transformed draft -> confirm -> separate SAM job. */
export function mountPromptBatch(T){
  const $=id=>document.getElementById(id),panel=document.createElement('details'),seen=new Map();panel.open=true;
  panel.innerHTML='<summary>저장 preset을 여러 이미지에 재사용</summary><p>대상은 위 전체/선택 이미지 설정입니다. ① 준비만 실행 → ② 이미지별 점·box 미리보기 → ③ 선택 행 검토 확정 → ④ 위 SAM 프롬프트를 “저장·검수한 재사용 프롬프트”로 선택하고 SAM만 실행하세요. 준비 과정은 기존 마스크를 바꾸지 않습니다.</p><label>일괄 재사용 preset <select id="batchPresetSelect"></select></label><label>일괄 좌표 변환 <select id="batchTransferMethod"><option value="normalized">영상 크기 비율 (정합 안 함)</option><option value="ecc">ECC 정합 (같은 배율·작은 회전/이동)</option><option value="ecc_masked">양쪽 제외 ECC · 중앙 50% (실험적)</option></select></label><button id="preparePromptBatch">대상 이미지 재사용 프롬프트 준비만 실행</button><button id="confirmPromptBatch">미리본 선택 행의 프롬프트 검토 확정</button><p>확정은 점 위치만의 검토입니다. 마스크·물질·GT 정확도를 확정하지 않습니다. 실패/취소된 새 준비는 이전 draft로 대체하지 않으며, SAM 출력은 기존 후보 옆에 추가됩니다.</p><table><thead><tr><th>확정 선택</th><th>이미지</th><th>재사용 상태</th><th>확인</th></tr></thead><tbody id="promptTransferRows"></tbody></table>';
  $('batchPromptSource').closest('label').after(panel);
  $('batchTransferMethod').value='ecc';
  const option=document.createElement('option');option.value='transferred';option.textContent='저장·검수한 재사용 프롬프트';$('batchPromptSource').append(option);
  const dialog=document.createElement('dialog');dialog.id='promptBatchDialog';
  dialog.innerHTML='<div class="dialog-heading"><h2>재사용 점·box 검토</h2><button id="closePromptBatch">닫기</button></div><p id="promptBatchPreviewInfo"></p><img id="promptBatchPreviewImage" style="max-width:100%;max-height:65vh" alt="재사용 프롬프트 미리보기"><p>청록=독립 자동점 · 초록/빨강=수동 +/−점 · 노랑=box · 분홍=분석 제외. 마스크 결과가 아닙니다.</p><button id="markPromptViewed">위치를 확인함 · 확정 대상에 선택</button>';
  document.body.append(dialog);let viewing=null,previewLoaded=false;
  $('closePromptBatch').onclick=()=>dialog.close();
  function previewGate(){$('markPromptViewed').disabled=T.busy||!previewLoaded}
  previewGate();window.addEventListener('tem:idle',previewGate);
  $('promptBatchPreviewImage').onload=()=>{previewLoaded=true;previewGate()};
  $('promptBatchPreviewImage').onerror=()=>{previewLoaded=false;previewGate();T.say('프롬프트 미리보기를 읽지 못했습니다. 다시 열어 확인하세요.')};
  T.promptTransferConfig=()=>({preset_id:$('batchPresetSelect').value,method:$('batchTransferMethod').value});
  function ids(){return $('batchScope').value==='all'?Object.keys(T.state.images):T.selectedImages.length?T.selectedImages:[T.current].filter(Boolean)}
  async function inspect(iid){
    const value=await T.api(`workflow/prompt-transfers/${iid}`,null,'GET');viewing={image_id:iid,signature:value.signature,draft_hash:value.draft_hash};
    previewLoaded=false;previewGate();
    $('promptBatchPreviewInfo').textContent=`${T.state.images[iid].name} · ${value.preset_id} · ${value.method}${value.ecc_score==null?'':' ECC '+value.ecc_score.toFixed(3)} · ${value.warnings.join(' ')}`;
    $('promptBatchPreviewImage').src=`/api/workflow/prompt-transfers/${iid}/preview.png?v=${value.draft_hash}`;dialog.showModal();
  }
  $('markPromptViewed').onclick=()=>{if(viewing&&previewLoaded&&!T.busy){seen.set(viewing.image_id,{...viewing,selected:true});dialog.close();render()}};
  function render(){
    const old=$('batchPresetSelect').value;$('batchPresetSelect').innerHTML=Object.values(T.state.prompt_presets||{}).map(p=>`<option value="${T.escape(p.id)}">${T.escape(p.id)}</option>`).join('');
    if(T.state.prompt_presets?.[old])$('batchPresetSelect').value=old;
    $('promptTransferRows').replaceChildren();
    for(const [iid,image] of Object.entries(T.state.images||{})){
      const value=T.state.prompt_transfers?.[iid],row=document.createElement('tr'),cell=document.createElement('td'),check=document.createElement('input');check.type='checkbox';check.dataset.transferId=iid;check.setAttribute('aria-label',image.name+' 프롬프트 검토 선택');
      if(seen.get(iid)?.draft_hash!==value?.draft_hash||value?.superseded_by)seen.delete(iid);
      check.disabled=!seen.has(iid);check.checked=!!seen.get(iid)?.selected;check.onchange=()=>{const entry=seen.get(iid);if(entry)entry.selected=check.checked};cell.append(check);row.append(cell);
      const name=document.createElement('td');name.textContent=image.name;row.append(name);
      const status=document.createElement('td');status.textContent=!value?'미준비':value.superseded_by?'새 준비 대기/실패/취소 · 이전 draft 실행 금지':`${value.preset_id} · ${value.draft.auto_points.length}+${value.draft.manual_points.length}점 · ${value.review_hash?'검토 기록 있음 (실행 시 최신 입력 확인)':'검토 필요'}`;row.append(status);
      const action=document.createElement('td'),view=document.createElement('button');view.textContent='점·box 보기';view.disabled=!value||!!value.superseded_by;view.onclick=()=>T.task(()=>inspect(iid));action.append(view);row.append(action);$('promptTransferRows').append(row);
    }
  }
  $('preparePromptBatch').onclick=()=>T.task(async()=>{
    const targets=ids();if(!targets.length)throw Error('대상 이미지를 선택하세요.');
    if(!await T.confirm(`${targets.length}장에 preset을 새로 준비할까요? 기존 mask는 보존되며 재사용 draft의 검토 상태는 해제됩니다. SAM은 실행하지 않습니다.`))return;
    await T.api('workflow/jobs/start',{image_ids:targets,steps:['prompt_transfer'],settings:{prompt_transfer:T.promptTransferConfig()}});seen.clear();window.dispatchEvent(new Event('tem:job-started'));
  });
  $('confirmPromptBatch').onclick=()=>T.task(async()=>{
    const entries=[...$('promptTransferRows').querySelectorAll('input:checked')].map(c=>seen.get(c.dataset.transferId)).filter(Boolean);
    if(!entries.length)throw Error('각 행의 미리보기를 보고 확인한 후 선택하세요.');
    if(!await T.confirm(`${entries.length}장의 변환된 점·box 위치를 검토했나요? 물질/마스크 GT 확정은 아닙니다.`))return;
    await T.api('workflow/prompt-transfers/confirm',{entries});await T.refresh();T.say('프롬프트만 검토 확정했습니다. SAM 일괄 프롬프트에서 저장·검수한 재사용 프롬프트를 선택하고 SAM만 별도로 실행하세요.');
  });
  window.addEventListener('tem:refreshed',render);render();return {render};
}
