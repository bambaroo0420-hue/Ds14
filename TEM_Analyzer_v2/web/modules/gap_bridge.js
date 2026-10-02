/* Two-layer gap preview and always-visible brush layer locks. No model required. */
export function mountGapBridge(T){
 const $=id=>document.getElementById(id);let token=null,previewImage=null,revision=null,imageReady=false;
 const locks=document.createElement('details');locks.id='brushLockPanel';locks.open=true;
 locks.innerHTML='<summary>브러시 · 레이어별 잠금 (프로젝트 전체)</summary><div id="brushLocks"></div><small id="brushTarget" role="status"></small>';
 $('canvasHost').before(locks);
 if(![...$('tool').options].some(o=>o.value==='roi'))$('tool').add(new Option('경계/회전 ROI 드래그','roi'));
 const panel=document.createElement('details');panel.open=true;panel.id='gapBridgePanel';
 panel.innerHTML=`<summary>두 레이어 사이 빈틈 · Gradient/DP 연결</summary>
 <p>두 마스크를 빈 영역 안의 공통 경계까지 확장합니다. 내부 구멍은 채우지 않습니다. 위/아래 또는 좌/우로 구분되는 층용입니다.</p>
 <label>레이어 A<select id="gapLayerA"></select></label><label>레이어 B<select id="gapLayerB"></select></label>
 <label>탐색 방향<select id="gapAxis"><option value="auto">자동 (위/아래 또는 좌/우)</option><option value="vertical">위/아래 층 · 세로 탐색</option><option value="horizontal">좌/우 층 · 가로 탐색</option></select></label>
 <label>최대 빈틈 폭 (원본 px, 1~200)<input id="gapMaxWidth" type="number" min="1" max="200" step="1" value="30"></label>
 <label>최소 Gradient (밝기 0~1 기준)<input id="gapMinGradient" type="number" min="0.001" max="1" step="0.005" value="0.015"></label>
 <label>DP 연속성<input id="gapSmooth" type="number" min="0" max="10" step="0.05" value="0.12"></label>
 <label>점간 최대 이동 (px)<input id="gapJump" type="number" min="1" max="20" value="4"></label>
 <label class="inline-check"><input id="gapUseROI" type="checkbox">그린 ROI 내부만</label>
 <label class="inline-check"><input id="gapMulti" type="checkbox">복수 Gradient 피크도 제안 (제3층 의심 · 반드시 검수)</label>
 <button id="gapPreview" class="primary">빈틈 경계 자동 제안 · 크게 보기</button><p id="gapSummary" role="status"></p>`;
 $('boundary').prepend(panel);
 const dialog=document.createElement('dialog');dialog.id='gapDialog';dialog.innerHTML=`<div class="dialog-heading"><h2>빈틈 경계 검수 · 아직 적용 안 됨</h2><button id="gapClose">닫기</button></div>
 <p>흰색/주황: 원래 두 경계 · 청록: 공통 경계 · 분홍: 새로 레이어에 포함될 빈 픽셀</p>
 <div class="gap-review"><img id="gapPreviewImage" alt="원본 영상 위의 두 레이어와 빈틈 보정 제안"><div><p id="gapReviewStats"></p><canvas id="gapProfile" width="420" height="200" aria-label="대표 스캔의 실제 Gradient와 DP 선택 위치"></canvas><p id="gapProfileInfo"></p><pre id="gapWarnings"></pre></div></div>
 <label><input id="gapConfirm" type="checkbox">이미지를 검수했고, 채울 영역은 제3층/공극이 아닌 선택한 두 층의 분할 누락입니다.</label>
 <p>이 확인은 재료 판별 모델이 대신하지 않습니다. 결과는 미검수 마스크로 저장되며 Undo 가능합니다.</p><button id="gapApply" disabled>검수한 빈틈 제안 적용</button>`;document.body.append(dialog);
 const reasonNames={unsupported_or_too_wide:'범위 밖/빈틈 폭 초과/스캔에 복수 구간',protected_excluded_or_other_layer:'보호·제외·다른 레이어',weak_gradient:'약한 Gradient',multiple_edges_possible_third_layer:'복수 경계: 제3층 가능성',short_run:'연속 스캔 부족',discontinuous_path:'연속 경로 실패',weak_selected_path:'선택 경로 신호 부족',topology_change:'객체/구멍 연결 구조 변화'};
 function owner(c){const seen=new Set();while(c&&c.layer_id==null&&c.parent&&!seen.has(c.id)){seen.add(c.id);c=T.state.candidates?.[T.current]?.find(v=>v.id===c.parent)}return T.state.layers?.find(l=>l.id===c?.layer_id)}
 function updateApply(){$('gapApply').disabled=T.busy||!token||!imageReady||!$('gapConfirm').checked||$('gapApply').dataset.hasChanges!=='true';}
 function invalidate(){token=null;imageReady=false;$('gapApply').disabled=true;$('gapConfirm').checked=false;}
 $('gapPreviewImage').onload=()=>{imageReady=!!token&&$('gapPreviewImage').naturalWidth>0;updateApply();};
 $('gapPreviewImage').onerror=()=>{imageReady=false;updateApply();$('gapReviewStats').textContent='제안 이미지를 불러오지 못했습니다. 다시 제안한 후 검수하세요. 적용은 차단됩니다.';};
 function render(){
  const layers=T.state.layers||[];
  $('brushLocks').innerHTML=layers.map(l=>`<button data-brush-lock="${l.id}" aria-pressed="${!!l.locked}" ${T.busy?'disabled':''}>${l.locked?'🔒':'🔓'} ${T.escape(l.name)} · ${l.locked?'잠김':'편집 가능'}</button>`).join('');
  for(const btn of $('brushLocks').querySelectorAll('button'))btn.onclick=()=>T.task(async()=>{const l=T.state.layers.find(x=>x.id===+btn.dataset.brushLock);await T.api('v2/lock',{layer_id:l.id,locked:!l.locked});await T.refresh()});
  const c=T.state.candidates?.[T.current]?.find(v=>v.id===T.selectedCandidate),l=owner(c);
  $('brushTarget').textContent=c?`브러시 대상 #${c.id} · ${l?l.name:'미배정'} · ${l?.locked?'잠겨 있어 적용 불가':'선택 mask만 수정 / 잠긴 타 레이어와 보호 픽셀 제외'}`:'브러시로 수정할 후보를 선택하세요.';
  $('applyBrush').disabled=T.busy||!c||!!l?.locked;
  for(const [id,fallback] of [['gapLayerA',0],['gapLayerB',1]]){const select=$(id),old=select.value;select.innerHTML=layers.map(l=>`<option value="${l.id}">${T.escape(l.name)}${l.locked?' 🔒':''}</option>`).join('');select.value=layers.some(l=>String(l.id)===old)?old:String(layers[fallback]?.id||'');}
  if(previewImage!==T.current||revision!==T.state.revision)invalidate();
  updateApply();
 }
 function plot(report){
  const c=$('gapProfile'),ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);ctx.fillStyle='#17212b';ctx.fillRect(0,0,c.width,c.height);
  const p=report.traces?.[0]?.profile;if(!p){$('gapProfileInfo').textContent='유효 경로가 없어 프로파일이 없습니다.';return;}
  const xmin=p.coordinate[0],xmax=p.coordinate.at(-1),ymax=Math.max(...p.gradient,0.001),px=x=>45+(x-xmin)/Math.max(1,xmax-xmin)*355,py=y=>155-y/ymax*125;
  ctx.strokeStyle='#8995a6';ctx.beginPath();ctx.moveTo(45,20);ctx.lineTo(45,155);ctx.lineTo(400,155);ctx.stroke();ctx.strokeStyle='#83baff';ctx.beginPath();p.gradient.forEach((y,i)=>i?ctx.lineTo(px(p.coordinate[i]),py(y)):ctx.moveTo(px(p.coordinate[i]),py(y)));ctx.stroke();
  ctx.strokeStyle='#00ffff';ctx.beginPath();ctx.moveTo(px(p.chosen),20);ctx.lineTo(px(p.chosen),155);ctx.stroke();ctx.fillStyle='#fff';ctx.font='12px sans-serif';ctx.fillText('Gradient',4,13);ctx.fillText(ymax.toFixed(3),4,34);ctx.fillText('0',25,157);ctx.fillText(String(xmin),45,176);ctx.fillText(String(xmax),375,176);ctx.fillText('원본 '+(p.axis==='vertical'?'y':'x')+' (px)',155,194);
  $('gapProfileInfo').textContent=`대표 스캔 ${p.scan}px · DP 위치 ${p.chosen+.5}px. 선택 두 경계 사이의 실제 밝기 변화입니다.`;
 }
 $('gapPreview').onclick=()=>T.task(async()=>{
  invalidate();if(!T.current)throw Error('이미지를 선택하세요.');if($('gapUseROI').checked&&!T.boundaryROI)throw Error('입력 방식에서 경계/회전 ROI를 그리세요.');
  const settings={method:'gradient_bridge',layer_a:+$('gapLayerA').value,layer_b:+$('gapLayerB').value,axis:$('gapAxis').value,max_gap:+$('gapMaxWidth').value,min_gradient:+$('gapMinGradient').value,smooth:+$('gapSmooth').value,jump:+$('gapJump').value,allow_multiple_edges:$('gapMulti').checked};
  const r=await T.api('workflow/boundary/preview',{image_id:T.current,settings,roi:$('gapUseROI').checked?T.boundaryROI:null});
  await T.refresh();token=r.token;previewImage=T.current;revision=T.state.revision;const report=r.reports[0];
  $('gapSummary').textContent=`채움 제안 ${r.changed_pixels}px · ${report.traces.length}개 연속 구간 · 아직 적용 안 됨`;$('gapReviewStats').textContent=$('gapSummary').textContent;
  $('gapWarnings').textContent=Object.entries(report.skipped).map(([k,v])=>`${reasonNames[k]||k}: ${v}개 스캔`).join('\n')+'\n'+report.note;
  $('gapPreviewImage').src=`/api/workflow/boundary/${token}.png`;$('gapConfirm').checked=false;$('gapApply').dataset.hasChanges=String(r.changed_pixels>0);plot(report);dialog.showModal();
 });
 $('gapConfirm').onchange=updateApply;
 $('gapApply').onclick=()=>T.task(async()=>{if(!token||!$('gapConfirm').checked)throw Error('검수 확인이 필요합니다.');const r=await T.api('workflow/boundary/apply',{token,confirmed_two_layers:true});invalidate();dialog.close();await T.refresh();$('gapSummary').textContent=`${r.changed_pixels}px 적용 완료 · 새 마스크 ${r.created.map(c=>'#'+c.id).join(', ')} · GT 검수는 별도입니다.`;T.say(`${r.changed_pixels}px 빈틈 보정 적용. 새 마스크를 검수하세요.`)});
 $('gapClose').onclick=()=>{invalidate();dialog.close()};dialog.addEventListener('cancel',invalidate);
 for(const event of ['tem:refreshed','tem:idle','tem:candidate'])window.addEventListener(event,render);
 if(T.state.layers)render();
 return {render};
}
