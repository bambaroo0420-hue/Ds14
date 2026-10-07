/* Instrument layout composed from the existing transactional controls. */
import {prepareComparisonImage} from './metrology.js?v=2.3.0';
export function mountWorkbench(T,selections){
  const $=id=>document.getElementById(id);T.selectedMaskIds=selections.ids;T.overlayMode='selected';
  const rail=document.createElement('aside');rail.id='workbenchRail';
  rail.innerHTML='<div id="dockHandle"><strong>MASK / LAYERS</strong><button id="floatAssignment">분리</button><button id="lockDock" aria-pressed="false">위치 잠금</button></div><p id="workbenchTarget"></p><label>표시 <select id="overlayMode"><option value="selected">선택 마스크</option><option value="layers">전체 레이어</option><option value="diagnostic">GT 진단 · 겹침/미지정/보호</option></select></label><label>선택 레이어 색 <input type="color" id="layerColor"></label><p>색은 표시용 · class ID는 유지됩니다.</p>';
  document.querySelector('main').prepend(rail);document.body.classList.add('instrument-ui');
  document.querySelector('header').append($('layerSelect').closest('label'));
  rail.append($('maskSelectionCount').closest('details'));rail.append($('candidateRows').closest('details'));
  $('maskSelectionCount').closest('details').before($('candidateRows').closest('.candidate-scroll'));
  const context=document.createElement('div');context.id='contextStrip';document.querySelector('.workspace').prepend(context);
  let floating=false,locked=false,drag=null;
  $('floatAssignment').onclick=()=>{if(locked)return;floating=!floating;rail.classList.toggle('floating',floating);document.body.classList.toggle('floating-rail',floating);$('floatAssignment').textContent=floating?'도킹':'분리';if(!floating){rail.style.left='';rail.style.top=''}T.resizeCanvas()};
  $('lockDock').onclick=()=>{locked=!locked;$('lockDock').textContent=locked?'위치 잠김':'위치 잠금';$('lockDock').setAttribute('aria-pressed',String(locked));$('floatAssignment').disabled=locked};
  $('dockHandle').onpointerdown=e=>{if(!floating||locked||e.target.closest('button'))return;const r=rail.getBoundingClientRect();drag=[e.clientX-r.left,e.clientY-r.top];e.currentTarget.setPointerCapture(e.pointerId)};
  $('dockHandle').onpointermove=e=>{if(!drag)return;rail.style.left=Math.max(0,Math.min(innerWidth-rail.offsetWidth,e.clientX-drag[0]))+'px';rail.style.top=Math.max(0,Math.min(innerHeight-80,e.clientY-drag[1]))+'px'};
  $('dockHandle').onpointerup=()=>drag=null;
  $('layerColor').onchange=()=>T.task(async()=>{await T.api('layers',{id:+$('layerSelect').value,color:$('layerColor').value});await T.refresh()});
  $('overlayMode').onchange=()=>T.task(async()=>{T.overlayMode=$('overlayMode').value;await T.reloadOverlay()});
  $('layerDrops').addEventListener('dragover',e=>{for(const el of $('layerDrops').children)el.classList.toggle('drop-target',el===e.target.closest('[data-drop-layer]'))});
  for(const name of ['dragleave','drop','dragend'])$('layerDrops').addEventListener(name,()=>{for(const el of $('layerDrops').children)el.classList.remove('drop-target')});
  $('layerDrops').addEventListener('click',e=>{const row=e.target.closest('[data-drop-layer]');if(!row?.dataset.dropLayer||T.busy)return;$('layerSelect').value=row.dataset.dropLayer;$('layerSelect').dispatchEvent(new Event('change'));render()});
  function render(){
    const layer=T.state.layers?.find(l=>l.id===+$('layerSelect').value),ids=selections.ids(),candidate=T.candidates().find(c=>c.id===T.selectedCandidate);
    const title=`${T.state.images?.[T.current]?.name||'이미지 없음'} · 선택 ${ids.length}개 · 편집 A #${candidate?.id||'—'} · ${layer?.name||'레이어 없음'}${layer?.locked?' 🔒':''}`;
    $('workbenchTarget').textContent=title;context.textContent=title+' · 도구: '+$('tool').selectedOptions[0]?.textContent;
    $('layerColor').value=layer?.color||'#28dc82';$('layerColor').disabled=T.busy||!layer;$('floatAssignment').disabled=locked;
    for(const row of $('layerDrops').querySelectorAll('[data-drop-layer]')){
      const lid=+row.dataset.dropLayer;if(!lid)continue;const masks=T.candidates().filter(c=>c.layer_id===lid);
      let info=row.querySelector('.layer-members');if(!info){info=document.createElement('div');info.className='layer-members';row.append(info)}
      info.textContent=`${masks.length}개: `+masks.map(c=>`#${c.id} ${c.name||c.source}`).join(', ');row.classList.toggle('current-layer',layer?.id===lid);
    }
  }
  for(const ev of ['tem:workbench-render','tem:refreshed','tem:candidate','tem:selection','tem:idle'])window.addEventListener(ev,render);
  $('layerSelect').addEventListener('change',render);$('tool').addEventListener('change',render);
  const auditPanel=document.createElement('details');auditPanel.open=true;
  auditPanel.innerHTML='<summary>GT 진단 · Full semantic 준비 상태</summary><p>빨강=클래스 겹침 · 노랑=미지정(틈/외부 포함) · 보라=불확실 · 분홍=제외 · 회색=명시적 배경 · 흰 사선=보호. 미지정 전체를 틈으로 자동 채우지 않습니다.</p><button id="auditGT">현재 레이어 진단</button><pre id="auditGTResult"></pre><button id="downloadOverlay">현재 표시 PNG 저장</button>';$('boundary').prepend(auditPanel);
  $('auditGT').onclick=()=>T.task(async()=>{const r=await T.api(`workbench/${T.current}/audit`,null,'GET');$('auditGTResult').textContent=`Full semantic: ${r.full_semantic_ready?'검수/커버리지 조건 충족 (정확도 보장 아님)':'미완료'}\n겹침 ${r.overlap_pixels}px / 미지정 ${r.unknown_pixels}px / 불확실 ${r.uncertain_pixels}px\n배경 ${r.background_pixels}px / 제외 ${r.excluded_pixels}px / 보호 ${r.protected_pixels}px\n미검수 mask: ${r.unreviewed_masks.join(', ')||'없음'}\n현재 유효 ${r.valid_pixels}px / 검수 export 유효 ${r.export_valid_pixels}px`;T.overlayMode='diagnostic';$('overlayMode').value='diagnostic';await T.reloadOverlay()});
  window.addEventListener('tem:refreshed',()=>{$('auditGTResult').textContent='현재 입력의 진단을 실행하세요. 이전 진단 수치는 입력 변경 후 유지하지 않습니다.'});
  $('downloadOverlay').onclick=()=>T.task(async()=>{T.download(await new Promise(resolve=>$('canvas').toBlob(resolve,'image/png')),'TEM_workbench.png')});
  const previousExport=$('exportGT').onclick;
  $('exportGT').onclick=async()=>{if(T.busy)return;try{const r=await T.api(`workbench/${T.current}/audit`,null,'GET');if(!r.full_semantic_ready&&!await T.confirm(`완전한 semantic GT가 아닙니다. 미지정 ${r.unknown_pixels}px, 겹침 ${r.overlap_pixels}px, 미검수 ${r.unreviewed_masks.length}개. 검수한 부분만 valid 마스크와 함께 출력할까요?`))return;previousExport()}catch(e){T.say(e.message)}};
  const evidence=document.createElement('details');evidence.open=true;evidence.innerHTML='<summary>회전·계측 근거 크게 보기</summary><button id="rotationEvidence">실제 기준점·피팅선 보기</button><button id="measurementEvidence">계측선·끝점 보기</button><p>회전: 초록=강한 가중치 점, 빨강=가중치 &lt; 0.5점, 청록=피팅선, 노랑=ROI. 계측: 청록=유효, 빨강=제외 표본, 노랑=끝점. 결과 표의 행을 클릭하면 해당 치수선만 표시합니다.</p>';$('measure').prepend(evidence);
  const dialog=document.createElement('dialog');dialog.id='evidenceDialog';dialog.innerHTML='<div class="dialog-heading"><h2 id="evidenceTitle"></h2><button id="closeEvidence">닫기</button></div><p id="evidenceInfo"></p><div class="alignment-comparison"><img id="evidenceBefore" alt="원본 좌표 근거"><img id="evidenceAfter" alt="회전 좌표 근거"></div><button id="saveEvidence">회전 좌표 PNG 저장</button>';document.body.append(dialog);
  $('closeEvidence').onclick=()=>dialog.close();let evidenceURL=null;
  async function show(kind,row=-1){
    if(!T.current)throw Error('이미지를 선택하세요.');const iid=T.current,revision=T.state.revision,info=await T.api(`workflow/status/${iid}`,null,'GET'),rotation=kind==='rotation';
    if(rotation?(!info.rotation||info.rotation_stale):(!info.measurement||info.measurement_stale))throw Error('현재 입력으로 회전/계측을 먼저 실행하세요.');
    const suffix=`&row=${row}&v=${revision}`,root=`/api/workbench/${iid}/${kind}.png`;
    const images=await Promise.all([prepareComparisonImage(root+'?aligned=false'+suffix,'원본 근거 영상'),prepareComparisonImage(root+'?aligned=true'+suffix,'회전 근거 영상')]);
    if(T.current!==iid||T.state.revision!==revision)throw Error('영상/입력이 바뀌었습니다. 근거 창을 다시 여세요.');
    $('evidenceBefore').src=images[0].src;$('evidenceAfter').src=images[1].src;evidenceURL=images[1].src;
    $('evidenceTitle').textContent=rotation?'실제 회전 기준 ↔ 보정 결과':'계측 위치 · 원본 ↔ 회전 좌표';
    $('evidenceInfo').textContent=rotation?`기준 ${JSON.stringify(info.rotation.config)} · 사용 경계 ${info.rotation.used_edge} · 보정각 ${info.rotation.transform.angle_deg.toFixed(4)}° · 잔차 ${info.rotation.fit.residual_px??'해당 없음'} px · ${(info.rotation.warnings||[]).join(' ')} ${info.rotation.fit.points?.length===2?'두 점의 잔차 0은 정확도 증거가 아닙니다.':''}`:`${info.measurement.axis} · ${row<0?'표시용 최대 약 150선 (전체 데이터는 ZIP)':JSON.stringify(info.measurement.rows[row])}`;dialog.showModal();
  }
  $('rotationEvidence').onclick=()=>T.task(()=>show('rotation'));$('measurementEvidence').onclick=()=>T.task(()=>show('measurement'));
  $('measureRows').addEventListener('click',e=>{const row=e.target.closest('tr');if(row)T.task(()=>show('measurement',[...$('measureRows').children].indexOf(row)))});
  $('saveEvidence').onclick=()=>T.task(async()=>{if(evidenceURL)T.download(await (await fetch(evidenceURL)).blob(),'TEM_metrology_evidence.png')});
  render();new ResizeObserver(()=>T.resizeCanvas()).observe(rail);
}
