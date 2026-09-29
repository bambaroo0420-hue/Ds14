export function mountMetrology(T) {
  const $=id=>document.getElementById(id);
  const auto=document.createElement('option');auto.value='auto';auto.textContent='자동: 단일 마스크 경계 / 여러 마스크 대표점';$('rotationMode').prepend(auto);$('rotationMode').value='auto';
  const direction=document.createElement('option');direction.value='image_direction';direction.textContent='영상 주 방향 보조 추정 (실험·레이어 경계 아님)';$('rotationMode').append(direction);
  const sampling=document.createElement('details');sampling.open=true;
  sampling.innerHTML='<summary>계측 표본·품질 기준 (일괄 처리에도 동일 적용)</summary><label>표본 구간 <select id="measureSampling"><option value="all">지정 좌표 전체 (기존 방식)</option><option value="component_center">각 연결 객체의 중앙 구간</option></select></label><label>중앙 구간 비율 (%) <input id="measureCenter" type="number" min="1" max="100" value="60"></label><label>최소 구간 길이 (px, 0: 제한 없음) <input id="measureMinimum" type="number" min="0" value="0" step="0.1"></label><label class="inline-check"><input id="measureSingle" type="checkbox">동일 객체에서 다중 교차하는 위치 제외</label><label class="inline-check"><input id="measureFrame" type="checkbox">원본 프레임에 닿는 끝점 제외</label><p>중앙 구간은 회전 후 각 연결 객체의 투영 폭/높이에 적용됩니다. 물질 구분이나 두께 정답을 추정하지 않습니다. 제외된 행과 원시 길이는 ZIP에 보존하며 평균에는 포함하지 않습니다.</p>';
  $('runMeasure').before(sampling);
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
    stop:$('measureStop').value===''?null:+$('measureStop').value,step:+$('measureStep').value,instance_id:$('measureInstance').value||null,
    sampling:{mode:$('measureSampling').value,center_fraction:+$('measureCenter').value/100,min_length_px:+$('measureMinimum').value,single_interval_only:$('measureSingle').checked,reject_frame_endpoints:$('measureFrame').checked}}}
  const statusName=s=>({ok:'유효',no_intersection:'교차 없음',invalid_region:'무효 영역',outside_component_window:'선택 구간 밖',multiple_intervals:'다중 교차',frame_endpoint:'프레임 접촉',below_min_length:'최소 길이 미만'}[s]||s);
  const number=v=>v==null?'—':Number(v).toFixed(3);
  function savedDescription(m){
    const p=m.sampling||{},s=m.summary,target=m.scope_id?'선택 집합 '+m.scope_id:'레이어 '+m.layer_id;
    return `저장된 결과: ${target} · ${m.axis==='cd'?'CD':'두께'} · ${p.mode==='component_center'?'객체 중앙 '+Math.round(p.center_fraction*100)+'%':'지정 좌표 전체'} · 다중 교차 ${p.single_interval_only?'제외':'포함'}, 프레임 끝점 ${p.reject_frame_endpoints?'제외':'포함'}, 최소 ${p.min_length_px||0}px · 유효 ${s.count}개, 평균 ${number(s.mean)}, 중앙값 ${number(s.median)}, 표준편차 ${number(s.std)} nm. 표 ${Math.min(300,m.rows.length)}/${m.rows.length}행 표시, ZIP에 전체 포함. 위 입력값을 바꾸면 다시 측정하세요.`;
  }
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
      if(r.measurement){$('measurementInfo').textContent=(r.measurement_stale?'만료된 결과: 다시 측정하세요. ':'')+(r.measurement.review_status==='provisional_unreviewed_masks'?'미검수 마스크의 잠정 계측값 · ':'검수 마스크 · ')+savedDescription(r.measurement)+' '+(r.measurement.warnings||[]).join(' ');showRows(r.measurement)}
    }).catch(e=>T.say(e.message))}
  }
  function showRows(result){$('measureRows').innerHTML=result.rows.slice(0,300).map(r=>`<tr><td>${r.position_px.toFixed(2)}</td><td>${r.segment??'—'} / 객체 ${r.component_id??'—'}</td><td>${r.length_nm==null?'—':r.length_nm.toFixed(4)}${r.length_nm==null&&r.raw_length_nm!=null?' (제외 원시값 '+r.raw_length_nm.toFixed(4)+')':''}</td><td>${T.escape([...new Set([r.status,...(r.quality_flags||[])])].map(statusName).join(' · '))}</td></tr>`).join('')}
  $('rotationUseROI').onclick=()=>{$('rotationROI').value=JSON.stringify(T.boundaryROI);T.say('SAM ROI 도구로 지정한 원본 구간을 사용합니다.')};
  $('rotationPreview').onclick=()=>T.task(async()=>{await T.api('workflow/rotation/preview',{image_id:T.current,config:rotationConfig()});await T.refresh()});
  $('rotationConfirm').onclick=()=>T.task(async()=>{await T.api('workflow/rotation/confirm',{image_id:T.current});await T.refresh()});
  $('runMeasure').onclick=()=>T.task(async()=>{await T.api('workflow/measurement',{image_id:T.current,config:measurementConfig()});await T.refresh()});
  $('downloadResults').onclick=()=>T.task(async()=>{const r=await T.api('workflow/export',{image_ids:T.selectedImages.length?T.selectedImages:[T.current],...T.exportOptions()});T.download(await r.blob(),'TEM_results.zip')});
  $('analysisScope').addEventListener('change',render);
  window.addEventListener('tem:scope-changed',render);
  window.addEventListener('tem:idle',()=>{$('rotationLayer').disabled=$('measureLayer').disabled=!!T.scopeId()});
  window.addEventListener('tem:refreshed',render);
  return {rotationConfig,measurementConfig,render};
}
