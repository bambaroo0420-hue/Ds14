/* A saved mask selection is a binary target, never an implicit material layer. */
export function mountScopes(T,selection){
  const $=id=>document.getElementById(id),panel=document.createElement('details');panel.open=true;
  panel.innerHTML='<summary>특정 마스크만 분석 · 부분 GT</summary><p>층 전체를 구분하지 않아도 됩니다. 목록에서 필요한 마스크만 선택하여 이미지마다 같은 집합 ID로 저장하세요. 선택 밖은 미지정이며, 선택 마스크끼리는 하나의 target 합집합입니다.</p><label>집합 ID <input id="maskScopeId" value="target" pattern="[A-Za-z0-9_-]{1,64}"></label><button id="saveMaskScope">선택 마스크 → 분석 대상 저장</button><button id="confirmMaskScope">이 선택 집합 검수 확정</button><p id="maskScopeInfo"></p><img id="maskScopePreview" class="result-preview" alt="선택 마스크 집합 미리보기"><label>회전·계측·GT·일괄 출력 범위 <select id="analysisScope"><option value="layers">기존 레이어 사용</option><option value="selection">저장한 선택 마스크 집합 사용</option></select></label><label class="inline-check"><input id="exportPartialGT" type="checkbox">ZIP에 검수된 GT 포함 (선택 집합이면 부분 GT)</label><p>검수 확정은 GT에만 필요합니다. 회전·계측은 미검수 마스크로도 가능하며 잠정값으로 표시됩니다. 일괄 처리에서 집합이 없는 이미지는 실패로 남고 다른 마스크로 대체하지 않습니다.</p>';
  $('maskSelectionCount').closest('details').after(panel);
  T.scopeId=()=>$('analysisScope').value==='selection'?$('maskScopeId').value.trim():null;
  T.exportOptions=()=>({scope_id:T.scopeId(),include_gt:$('exportPartialGT').checked});
  const dialog=document.createElement('dialog');dialog.id='scopeCompareDialog';
  dialog.innerHTML='<div class="dialog-heading"><h2>분석에 쓰는 선택 집합 전체</h2><button id="closeScopeCompare">닫기</button></div><p id="scopeCompareInfo"></p><img id="scopeCompareImage" style="max-width:100%;max-height:72vh" alt="분석 대상 선택 집합 전체"><p>초록색은 선택된 마스크들의 유효 target 합집합입니다. 미선택 영역은 unknown입니다. 기본 캔버스의 현재 후보 한 개 표시와 다릅니다.</p>';
  document.body.append(dialog);$('closeScopeCompare').onclick=()=>dialog.close();
  function showTarget(){
    const key=T.scopeId(),s=T.state.mask_scopes?.[T.current]?.[key];if(!key||!s){T.say('현재 이미지에 저장된 선택 집합 모드가 필요합니다.');return}
    $('scopeCompareInfo').textContent=`${T.state.images[T.current].name} · 집합 ${key} · mask ${s.candidate_ids.join(', ')} · 검수/정확도는 별도 확인 필요`;
    $('scopeCompareImage').src=`/api/workflow/scopes/${T.current}/${encodeURIComponent(key)}.png?v=${T.state.revision}`;dialog.showModal();
  }
  const mirrors=[];
  for(const page of ['measure','batch']){
    const box=document.createElement('div');box.className='scope-banner';
    box.innerHTML=`<label>현재 분석 범위 <select id="scopeMode_${page}"><option value="layers">기존 레이어 사용</option><option value="selection">저장한 선택 마스크 집합 사용</option></select></label><p id="scopeNote_${page}"></p><button id="scopeShow_${page}">선택 집합 전체 크게 보기</button><button id="scopeEdit_${page}">SAM 화면에서 선택 집합 편집</button>`;
    $(page).querySelector('h2').after(box);mirrors.push(page);
    $(`scopeMode_${page}`).onchange=()=>{$('analysisScope').value=$(`scopeMode_${page}`).value;changed()};
    $(`scopeEdit_${page}`).onclick=()=>document.querySelector('[data-page="sam"]').click();
    $(`scopeShow_${page}`).onclick=showTarget;
  }
  function changed(){render();window.dispatchEvent(new Event('tem:scope-changed'))}
  function render(){
    const key=$('maskScopeId').value.trim(),s=T.state.mask_scopes?.[T.current]?.[key];
    $('maskScopeInfo').textContent=s?`${key}: mask ${s.candidate_ids.join(', ')} · ${s.review_hash?'검수 기록 있음 (GT 출력 시 최신 입력 확인)':'미검수'}`:'현재 이미지에 저장한 선택 집합이 없습니다.';
    if(s)$('maskScopePreview').src=`/api/workflow/scopes/${T.current}/${encodeURIComponent(key)}.png?v=${T.state.revision}`;else $('maskScopePreview').removeAttribute('src');
    for(const page of mirrors){
      $(`scopeMode_${page}`).value=$('analysisScope').value;
      const total=Object.keys(T.state.images).length,ready=Object.keys(T.state.images).filter(i=>T.state.mask_scopes?.[i]?.[key]).length;
      $(`scopeNote_${page}`).textContent=T.scopeId()?`선택 집합 ID: ${key} · 현재 이미지 ${s?'mask '+s.candidate_ids.join(', '):'집합 없음: 실행 시 실패'} · 프로젝트 ${ready}/${total}장에 저장됨. 미선택은 unknown입니다. 왼쪽 캔버스는 현재 후보 한 개일 수 있으므로 전체 선택은 크게 보기에서 확인하세요.`:'레이어 기준입니다. 특정 마스크만 쓰려면 저장한 선택 집합으로 전환하세요.';
    }
  }
  $('maskScopeId').onchange=changed;
  $('analysisScope').addEventListener('change',changed);
  $('saveMaskScope').onclick=()=>T.task(async()=>{await T.api('workflow/scopes/save',{image_id:T.current,scope_id:$('maskScopeId').value.trim(),candidate_ids:selection.ids()});$('analysisScope').value='selection';await T.refresh();T.say('선택 집합 저장됨. 회전·계측에 사용할 수 있습니다. 부분 GT는 미리보기를 검수한 후 확정하세요.')});
  $('confirmMaskScope').onclick=()=>T.task(async()=>{if(!await T.confirm('선택 집합 미리보기가 의도한 target인지 확인했나요? 선택 밖은 unknown이며 전체 물질 GT가 아닙니다.'))return;await T.api('workflow/scopes/confirm',{image_id:T.current,scope_id:$('maskScopeId').value.trim()});await T.refresh()});
  window.addEventListener('tem:refreshed',render);return {render};
}
