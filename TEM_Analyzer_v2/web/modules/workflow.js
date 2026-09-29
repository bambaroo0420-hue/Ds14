import {mountSelection} from './selection.js?v=2.2.0';
import {mountMetrology} from './metrology.js?v=2.2.0';
import {mountBatch} from './batch.js?v=2.2.0';
import {mountScopes} from './scopes.js?v=2.2.0';
import {mountPromptTransfer} from './prompt_transfer.js?v=2.2.0';
const T=window.TEM,$=id=>document.getElementById(id);let boundaryToken=null,boundaryImage=null;
const selections=mountSelection(T),scopes=mountScopes(T,selections),metrology=mountMetrology(T),batch=mountBatch(T,metrology);
const promptTransfer=mountPromptTransfer(T);
const ocrMode=document.createElement('label');ocrMode.className='inline-check';ocrMode.innerHTML='<input id="enhancedOCR" type="checkbox" checked>확대 재검출 OCR (약한 문자 보완, 더 느림)';$('detectAnnotations').before(ocrMode);
function render(){
  $('samImageSelect').innerHTML=Object.entries(T.state.images||{}).map(([id,x])=>`<option value="${id}">${T.escape(x.name)}</option>`).join('');$('samImageSelect').value=T.current||'';
  const masks=(T.state.candidates?.[T.current]||[]).filter(c=>!c.deleted&&c.active!==false);
  $('samImageStatus').textContent=`전체 ${Object.keys(T.state.images||{}).length}개 이미지 · 현재 후보 ${masks.length}개 · 레이어 미지정 ${masks.filter(c=>c.layer_id==null).length}개`;
  if($('featureInfo').dataset.image!==T.current){$('featureInfo').textContent='';$('featureInfo').dataset.image=T.current;$('featureFilteredPreview').removeAttribute('src');$('featureProposalPreview').removeAttribute('src')}
  const enabled=!!T.state.legacy_templates_enabled;
  $('toggleLegacyTemplates').textContent=enabled?'기존 위치 템플릿 끄기':'기존 위치 템플릿 켜기';
  $('toggleLegacyTemplates').setAttribute('aria-pressed',String(enabled));
  $('legacyTemplateStatus').textContent=enabled?'활성 — 저장한 고정 위치 박스도 분석에서 제외됩니다.':'비활성 — 고정 위치 박스는 표시·적용하지 않습니다. OCR 박스는 별도입니다.';
  $('legacyTemplateControls').disabled=!enabled;$('legacyBatchControls').disabled=!enabled;
  for(const op of $('tool').options)if(['scale','text','scale_text_roi','sample_roi','magnification_roi'].includes(op.value))op.disabled=!enabled;
  if($('tool').selectedOptions[0]?.disabled)$('tool').value='view';
  const old=$('referenceImage').value;
  $('referenceImage').innerHTML=Object.entries(T.state.images||{}).map(([id,x])=>`<option value="${id}">${T.escape(x.name)}</option>`).join('');
  if(T.state.images?.[old])$('referenceImage').value=old;
  $('layerDrops').innerHTML=(T.state.layers||[]).map(l=>`<div tabindex="0" data-drop-layer="${l.id}" style="border-left:5px solid ${l.color}">${T.escape(l.name)} ${l.locked?'🔒':''} <small>마스크 놓기</small></div>`).join('')+'<div data-drop-layer="">레이어 지정 해제</div>';
  if(boundaryImage!==T.current){boundaryToken=null;boundaryImage=T.current;$('layerBoundaryPreviewImage').removeAttribute('src')}
  const p=T.state.annotation_proposals?.[T.current];
  $('annotationInfo').textContent=p?`${p.regions.length}개 검출 · ${p.scale.nm_per_px?Number(p.scale.nm_per_px).toFixed(6)+' nm/px':'스케일 미검출'} · ${p.scale.ambiguous?'복수 후보 검토 필요':''}`:'이미지 전체에서 문자와 바를 검출합니다.';
  $('annotationRows').innerHTML=p?p.regions.map((r,i)=>`<tr><td><input type="checkbox" ${r.recommended===false?'':'checked'} data-region-index="${i}" aria-label="제외 박스 ${i+1}">${T.escape(r.kind)}</td><td>${T.escape(r.text)} ${T.escape(r.reason||'')}</td><td>${r.box.map(v=>Math.round(v)).join(', ')}</td></tr>`).join(''):'';
  if(p)$('annotationPreview').src=`/api/workflow/annotations/${T.current}.png?v=${T.state.revision}`;else $('annotationPreview').removeAttribute('src');
  selections.render();
}
$('toggleLegacyTemplates').onclick=()=>T.task(async()=>{await T.api('workflow/templates/enabled',{enabled:!T.state.legacy_templates_enabled});T.clearRegionDraft();await T.refresh()});
$('samImageSelect').onchange=e=>T.switchImage(e.target.value);
$('detectAnnotations').onclick=()=>T.task(async()=>{await T.api('workflow/annotations/detect',{image_id:T.current,ocr_dir:$('ocrDir').value,enhanced_ocr:$('enhancedOCR').checked});await T.refresh()});
$('applyAnnotations').onclick=()=>T.task(async()=>{const indices=[...document.querySelectorAll('[data-region-index]:checked')].map(e=>+e.dataset.regionIndex);await T.api('workflow/annotations/apply',{image_id:T.current,region_indices:indices});T.clearRegionDraft();await T.refresh();T.say('제외 영역 적용됨. 스케일 제안값은 별도로 확인·확정하세요.')});
$('matchLayers').onclick=()=>T.task(async()=>{const r=await T.api('workflow/layers/match',{reference_image:$('referenceImage').value,image_id:T.current,threshold:+$('matchThreshold').value});await T.refresh();T.say(`${r.proposals.length}개 후보 대응 제안: 결과를 검수하세요.`)});
for(const [id,delta] of [['layerUp',-1],['layerDown',1]])$(id).onclick=()=>T.task(async()=>{
  const ids=T.state.layers.map(l=>l.id),i=ids.indexOf(+$('layerSelect').value),j=i+delta;if(j<0||j>=ids.length)return;
  [ids[i],ids[j]]=[ids[j],ids[i]];await T.api('workflow/layers/order',{layer_ids:ids});await T.refresh();
});
$('inspectConflicts').onclick=()=>T.task(async()=>{$('conflictReport').textContent=JSON.stringify(await T.api(`workflow/conflicts/${T.current}?max_gap=${+$('layerGap').value}`,null,'GET'),null,2)});
$('layerBoundaryPreview').onclick=()=>T.task(async()=>{
  if($('boundaryUseROI').checked&&!T.boundaryROI)throw Error('먼저 캔버스에서 ROI 구간을 지정하세요.');
  const r=await T.api('workflow/boundary/preview',{image_id:T.current,settings:{radius:+$('layerRadius').value,max_gap:+$('layerGap').value},roi:$('boundaryUseROI').checked?T.boundaryROI:null});
  boundaryToken=r.token;boundaryImage=T.current;$('conflictReport').textContent=JSON.stringify(r,null,2);$('layerBoundaryPreviewImage').src=`/api/workflow/boundary/${r.token}.png`;
});
$('layerBoundaryApply').onclick=()=>T.task(async()=>{if(!boundaryToken)throw Error('레이어 경계를 먼저 제안하세요');await T.api('workflow/boundary/apply',{token:boundaryToken});boundaryToken=null;await T.refresh();T.say('경계 적용됨. 변경 마스크를 검수 확정하세요.')});
$('confirmGT').onclick=()=>T.task(async()=>{const r=await T.api('workflow/gt/confirm',{image_id:T.current,scope_id:T.scopeId()});T.say(`GT 검수 완료: 유효 ${r.valid_pixels}px, 미지정 ${r.unknown_pixels}px`);await T.refresh()});
$('restoreImage').onclick=()=>T.task(async()=>{const items=await T.api('workflow/trash',null,'GET');if(!items.length)throw Error('복원할 삭제 이미지가 없습니다');await T.api('workflow/trash/restore',{trash_id:items[0].id});await T.refresh();T.say('최근 삭제 이미지 복원됨')});
window.addEventListener('tem:refreshed',render);
if(T.state.layers){render();metrology.render()}
