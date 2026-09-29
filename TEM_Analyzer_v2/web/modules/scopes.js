/* A saved mask selection is a binary target, never an implicit material layer. */
export function mountScopes(T,selection){
  const $=id=>document.getElementById(id),panel=document.createElement('details');panel.open=true;
  panel.innerHTML='<summary>특정 마스크만 분석 · 부분 GT</summary><p>층 전체를 구분하지 않아도 됩니다. 목록에서 필요한 마스크만 선택하여 이미지마다 같은 집합 ID로 저장하세요. 선택 밖은 미지정이며, 선택 마스크끼리는 하나의 target 합집합입니다.</p><label>집합 ID <input id="maskScopeId" value="target" pattern="[A-Za-z0-9_-]{1,64}"></label><button id="saveMaskScope">선택 마스크 → 분석 대상 저장</button><button id="confirmMaskScope">이 선택 집합 검수 확정</button><p id="maskScopeInfo"></p><img id="maskScopePreview" class="result-preview" alt="선택 마스크 집합 미리보기"><label>회전·계측·GT·일괄 출력 범위 <select id="analysisScope"><option value="layers">기존 레이어 사용</option><option value="selection">저장한 선택 마스크 집합 사용</option></select></label><label class="inline-check"><input id="exportPartialGT" type="checkbox">ZIP에 검수된 GT 포함 (선택 집합이면 부분 GT)</label><p>검수 확정은 GT에만 필요합니다. 회전·계측은 미검수 마스크로도 가능하며 잠정값으로 표시됩니다. 일괄 처리에서 집합이 없는 이미지는 실패로 남고 다른 마스크로 대체하지 않습니다.</p>';
  $('maskSelectionCount').closest('details').after(panel);
  T.scopeId=()=>$('analysisScope').value==='selection'?$('maskScopeId').value.trim():null;
  T.exportOptions=()=>({scope_id:T.scopeId(),include_gt:$('exportPartialGT').checked});
  function render(){
    const key=$('maskScopeId').value.trim(),s=T.state.mask_scopes?.[T.current]?.[key];
    $('maskScopeInfo').textContent=s?`${key}: mask ${s.candidate_ids.join(', ')} · ${s.review_hash?'검수 기록 있음 (GT 출력 시 최신 입력 확인)':'미검수'}`:'현재 이미지에 저장한 선택 집합이 없습니다.';
    if(s)$('maskScopePreview').src=`/api/workflow/scopes/${T.current}/${encodeURIComponent(key)}.png?v=${T.state.revision}`;else $('maskScopePreview').removeAttribute('src');
  }
  $('maskScopeId').onchange=render;
  $('saveMaskScope').onclick=()=>T.task(async()=>{await T.api('workflow/scopes/save',{image_id:T.current,scope_id:$('maskScopeId').value.trim(),candidate_ids:selection.ids()});$('analysisScope').value='selection';await T.refresh();T.say('선택 집합 저장됨. 회전·계측에 사용할 수 있습니다. 부분 GT는 미리보기를 검수한 후 확정하세요.')});
  $('confirmMaskScope').onclick=()=>T.task(async()=>{if(!await T.confirm('선택 집합 미리보기가 의도한 target인지 확인했나요? 선택 밖은 unknown이며 전체 물질 GT가 아닙니다.'))return;await T.api('workflow/scopes/confirm',{image_id:T.current,scope_id:$('maskScopeId').value.trim()});await T.refresh()});
  window.addEventListener('tem:refreshed',render);return {render};
}
