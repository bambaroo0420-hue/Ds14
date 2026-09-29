export function mountMetrology(T) {
  const $=id=>document.getElementById(id);
  const auto=document.createElement('option');auto.value='auto';auto.textContent='자동: 단일 마스크 경계 / 여러 마스크 대표점';$('rotationMode').prepend(auto);$('rotationMode').value='auto';
  const direction=document.createElement('option');direction.value='image_direction';direction.textContent='영상 주 방향 보조 추정 (실험·레이어 경계 아님)';$('rotationMode').append(direction);
  const residual=r=>r.fit.residual_px==null?'해당 없음 (영상 방향)':r.fit.residual_px.toFixed(2)+' px';
  $('runMeasure').textContent='현재 레이어로 계측 (GT 불필요)';$('downloadResults').textContent='회전 · 좌표 변환 · 계측 ZIP (GT 별도)';
  const compare=document.createElement('button');compare.id='openAlignmentCompare';compare.textContent='원본 · 회전 결과 크게 비교';$('alignedPreview').after(compare);
  const dialog=document.createElement('dialog');dialog.id='alignmentCompare';
  dialog.innerHTML='<div class="dialog-heading"><h2>원본 ↔ 회전 보정</h2><button id="closeAlignmentCompare">닫기</button></div><p id="alignmentCompareInfo"></p><div class="alignment-comparison"><figure><figcaption>원본 좌표계 · 기울어진 입력</figcaption><img id="alignmentBefore" alt="회전 전 원본"></figure><figure><figcaption>정렬 좌표계 · 회전 결과</figcaption><img id="alignmentAfter" alt="회전 보정 결과"></figure></div><p>원본은 보존됩니다. 선택 방식에 따라 SAM 경계·대응점·영상 주 방향을 사용합니다. GT·경계 보정은 필수가 아닙니다.</p>';
  document.body.append(dialog);$('closeAlignmentCompare').onclick=()=>dialog.close();
  compare.onclick=()=>T.task(async()=>{if(!T.current)throw Error('이미지를 선택하세요.');const r=await T.api(`workflow/status/${T.current}`,null,'GET');if(!r.rotation||r.rotation_stale)throw Error('현재 입력으로 회전을 먼저 제안하세요.');$('alignmentBefore').src=`/api/images/${T.current}.png`;$('alignmentAfter').src=`/api/workflow/rotation/${T.current}.png?v=${T.state.revision}`;$('alignmentCompareInfo').textContent=`${T.state.images[T.current].name} · 보정각 ${r.rotation.transform.angle_deg.toFixed(4)}° · 잔차 ${residual(r.rotation)} · ${r.rotation.confirmed?'회전 확정':'회전 검토 필요'} ${(r.rotation.warnings||[]).join(' ')}`;dialog.showModal()});
  function parsed(id,fallback){const value=$(id).value.trim();return value?JSON.parse(value):fallback}
  function rotationConfig(){return {scope_id:T.scopeId(),layer_id:+$('rotationLayer').value,edge:$('rotationEdge').value,mode:$('rotationMode').value,
    roi:parsed('rotationROI',null),points:parsed('rotationPoints',[]),target_angle:+$('rotationTarget').value,max_residual:+$('rotationResidual').value}}
  function measurementConfig(){return {scope_id:T.scopeId(),layer_id:+$('measureLayer').value,axis:$('measureAxis').value,start:+$('measureStart').value,
    stop:$('measureStop').value===''?null:+$('measureStop').value,step:+$('measureStep').value,instance_id:$('measureInstance').value||null}}
  function render(){
    for(const id of ['rotationLayer','measureLayer']){const old=$(id).value;$(id).innerHTML=T.state.layers.map(l=>`<option value="${l.id}">${T.escape(l.name)}</option>`).join('');if(T.state.layers.some(l=>String(l.id)===old))$(id).value=old}
    $('measureRows').innerHTML='';$('rotationInfo').textContent='기준 레이어를 선택해 회전각을 제안하세요.';
    $('measurementInfo').textContent=`${T.scopeId()?'선택 마스크 집합 '+T.scopeId():'레이어'} → 회전·스케일 확인 후 계측. 경계 보정·GT 확정은 선택 사항입니다. 미검수 마스크 결과는 잠정값입니다.`;
    $('runMeasure').textContent=T.scopeId()?'선택 마스크로 계측 (레이어·GT 불필요)':'현재 레이어로 계측 (GT 불필요)';
    $('rotationLayer').disabled=$('measureLayer').disabled=!!T.scopeId();
    $('alignedPreview').removeAttribute('src');
    if(T.current){const iid=T.current;T.api(`workflow/status/${iid}`,null,'GET').then(r=>{
      if(iid!==T.current)return;
      if(r.rotation){$('rotationInfo').textContent=`각도 ${r.rotation.transform.angle_deg.toFixed(4)}° · 잔차 ${residual(r.rotation)} · ${r.rotation_stale?'입력 변경: 재계산':r.rotation.confirmed?'확정':'검토 필요'} ${(r.rotation.warnings||[]).join(' ')}`;
        if(!r.rotation_stale)$('alignedPreview').src=`/api/workflow/rotation/${iid}.png?v=${T.state.revision}`;}
      if(r.measurement){$('measurementInfo').textContent=(r.measurement_stale?'만료된 결과: 다시 측정하세요. ':'')+(r.measurement.review_status==='provisional_unreviewed_masks'?'미검수 마스크의 잠정 계측값 · ':'검수 마스크 · ')+JSON.stringify(r.measurement.summary);showRows(r.measurement)}
    }).catch(e=>T.say(e.message))}
  }
  function showRows(result){$('measureRows').innerHTML=result.rows.slice(0,300).map(r=>`<tr><td>${r.position_px.toFixed(2)}</td><td>${r.segment??'—'}</td><td>${r.length_nm==null?'—':r.length_nm.toFixed(4)}</td><td>${T.escape(r.status)}</td></tr>`).join('')}
  $('rotationUseROI').onclick=()=>{$('rotationROI').value=JSON.stringify(T.boundaryROI);T.say('SAM ROI 도구로 지정한 원본 구간을 사용합니다.')};
  $('rotationPreview').onclick=()=>T.task(async()=>{await T.api('workflow/rotation/preview',{image_id:T.current,config:rotationConfig()});await T.refresh()});
  $('rotationConfirm').onclick=()=>T.task(async()=>{await T.api('workflow/rotation/confirm',{image_id:T.current});await T.refresh()});
  $('runMeasure').onclick=()=>T.task(async()=>{await T.api('workflow/measurement',{image_id:T.current,config:measurementConfig()});await T.refresh()});
  $('downloadResults').onclick=()=>T.task(async()=>{const r=await T.api('workflow/export',{image_ids:T.selectedImages.length?T.selectedImages:[T.current],...T.exportOptions()});T.download(await r.blob(),'TEM_results.zip')});
  $('analysisScope').addEventListener('change',render);
  window.addEventListener('tem:idle',()=>{$('rotationLayer').disabled=$('measureLayer').disabled=!!T.scopeId()});
  window.addEventListener('tem:refreshed',render);
  return {rotationConfig,measurementConfig,render};
}
