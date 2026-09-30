const $=id=>document.getElementById(id);
let state={},current=null,base=new Image(),mask=new Image(),coverage=new Image(),showCov=false,tint=null,points=[],box=null,roi=null,strokes=[],activeStroke=null,drag=null,scaleDraft=null,textDraft=[],zoom=1,panX=0,panY=0,fit=1;
let gridPoints=[],mlPoints=[],displayMode='candidate',overlayVersion=0,loadedImage=null;
let templateDraft=null,analysisRegionDraft=null;
let preprocessingPreview=null,preprocessingVersion=0,activePage='images';
let uiBusy=false;
let displayedScaleKey=null;
let candidateSort={key:'id',direction:1},scaleBar=null,barProposals=[],imageSwitchBusy=false;
const imageDrafts={};
const canvas=$('canvas'),ctx=canvas.getContext('2d'),host=$('canvasHost');
function say(msg){$('message').textContent=msg;$('message').style.display='block';setTimeout(()=>$('message').style.display='none',4500)}
async function confirmAction(message){return typeof window!=='undefined'&&window.TEM?.confirm?window.TEM.confirm(message):confirm(message)}
async function responseError(r){let x;try{x=await r.json()}catch{x={detail:`HTTP ${r.status||''} ${r.statusText||'서버 오류'} · 서버 터미널의 오류 기록을 확인하세요.`}}return typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x)}
async function api(path,body,method='POST') {const r=await fetch('/api/'+path,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});if(!r.ok)throw Error(await responseError(r));return r.headers.get('content-type')?.includes('application/json')?r.json():r}
async function task(fn){if(uiBusy)return;uiBusy=true;const controls=[...document.querySelectorAll('button,input,select')].map(e=>[e,e.disabled]);for(const [e] of controls)e.disabled=true;$('status').textContent='처리 중...';try{await fn();$('status').textContent='완료'}catch(e){say(e.message);$('status').textContent='오류: '+e.message}finally{uiBusy=false;for(const [e,disabled] of controls)e.disabled=disabled;renderGallery();window.dispatchEvent(new Event('tem:idle'))}}
async function refresh(){
 const oldCandidate=$('candidateSelect').value,oldLayer=$('layerSelect').value;
 state=await api('state',null,'GET');
 if(state.storage_error){$('status').textContent=state.storage_error;say(state.storage_error)}
 $('imageSelect').innerHTML=Object.entries(state.images).map(([id,x])=>`<option value="${id}">${escapeHtml(x.name)}</option>`).join('');
 if(!current||!state.images[current])current=Object.keys(state.images)[0]||null;
 $('imageSelect').value=current||'';
 $('templateSelect').innerHTML=Object.values(state.templates).map(t=>`<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
 $('templateSelect').value=state.selected_template;$('templateName').value=state.templates[state.selected_template].name;
 $('layerSelect').innerHTML=state.layers.map(x=>`<option value="${x.id}">${escapeHtml(x.name)}</option>`).join('');
 if(state.layers.some(x=>String(x.id)===oldLayer))$('layerSelect').value=oldLayer;
 $('candidateSelect').innerHTML=sortedCandidates().map(c=>`<option value="${c.id}">${c.id}</option>`).join('');
 if((state.candidates[current]||[]).some(c=>String(c.id)===oldCandidate))$('candidateSelect').value=oldCandidate;
 if(current!==loadedImage||(!current&&base.naturalWidth)){
  if(loadedImage)imageDrafts[loadedImage]={points,gridPoints,mlPoints,box,roi,strokes};
  const d=imageDrafts[current]||{};points=d.points||[];gridPoints=d.gridPoints||[];mlPoints=d.mlPoints||[];box=d.box||null;roi=d.roi||null;strokes=d.strokes||[];scaleDraft=null;textDraft=[];if(!state.legacy_templates_enabled){templateDraft=null;analysisRegionDraft=null}tint=null;showCov=false;overlayVersion++;await loadImage();restoreScale();
 }
 const scaleKey=JSON.stringify([current,state.scale[current]]);if(scaleKey!==displayedScaleKey){restoreScale();displayedScaleKey=scaleKey}
 renderGallery();renderCandidates();renderBatchResults();await loadPreprocessingPreview();
 $('modelInfo').textContent=JSON.stringify(state.model||{status:'모델 미로드'},null,2);
 $('scaleInfo').textContent=state.scale[current]?.nm_per_px?`${(1/state.scale[current].nm_per_px).toFixed(6)} px/nm · ${state.scale[current].nm_per_px.toFixed(6)} nm/px (${state.scale[current].confirmed?'확정':'제안·검수 필요'})`:'스케일 미확정';
 if(displayMode==='layer')await loadLayer();else await loadMask(false);
 if(['failed','error'].includes(state.preprocessing?.[current]?.scale_status))$('scaleInfo').textContent+=' · 일괄 검출 실패: 수동 재설정 필요';
 renderRegionSummary();updatePromptCount();redraw();
 if(typeof window!=='undefined'&&window.dispatchEvent&&typeof CustomEvent!=='undefined')window.dispatchEvent(new CustomEvent('tem:refreshed'));
}
function escapeHtml(s){return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')}
function selected(){return Number($('candidateSelect').value)||null}
async function loadImage(){
 loadedImage=current;if(!current){base=new Image();redraw();return}
 await new Promise((resolve,reject)=>{base=new Image();base.onload=()=>{fit=Math.min(host.clientWidth/base.width,host.clientHeight/base.height);zoom=1;panX=(host.clientWidth-base.width*fit)/2;panY=(host.clientHeight-base.height*fit)/2;resolve()};base.onerror=()=>reject(Error('이미지를 불러올 수 없습니다.'));base.src='/api/images/'+current+'.png';});
}
async function showBinary(url,color){
 const token=++overlayVersion;tint=null;showCov=false;redraw();
 const img=await new Promise((resolve,reject)=>{let im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(Error('마스크를 불러올 수 없습니다.'));im.src=url});
 if(token!==overlayVersion)return;
 let c=document.createElement('canvas');c.width=img.width;c.height=img.height;
 let x=c.getContext('2d');x.drawImage(img,0,0);let d=x.getImageData(0,0,c.width,c.height);
 let rgb=color.replace('#','').match(/.{2}/g)?.map(v=>parseInt(v,16))||[41,220,130];
 for(let i=0;i<d.data.length;i+=4){let inside=d.data[i]>127;d.data[i]=rgb[0];d.data[i+1]=rgb[1];d.data[i+2]=rgb[2];d.data[i+3]=inside?255:0;}
 x.putImageData(d,0,0);tint=c;redraw();
}
async function loadMask(changeMode=true){
 if(changeMode)displayMode='candidate';renderCandidates();
 let id=selected();let c=(state.candidates[current]||[]).find(x=>x.id===id);
 $('selectionInfo').textContent=c?`후보 #${id} / ${c.area}px / 예측 IoU${state.model?.score_calibrated===false?' (학습 후 미보정)':''} ${c.predicted_iou==null?'수동 수정':c.predicted_iou.toFixed(3)}`:'선택된 후보 없음';
 if(!current||!c){overlayVersion++;tint=null;showCov=false;redraw();return;}
 await showBinary('/api/masks/'+current+'/'+id+'.png?'+Date.now(),'#29dc82');
}
async function loadLayer(){
 displayMode='layer';let id=+$('layerSelect').value,layer=state.layers.find(x=>x.id===id);
 $('selectionInfo').textContent=layer?`레이어 ${layer.name} / ${(state.candidates[current]||[]).filter(c=>c.layer_id===id).length}개 마스크 표시`:'선택된 레이어 없음';
 if(!current||!layer){overlayVersion++;tint=null;showCov=false;redraw();return;}
 await showBinary('/api/layer-mask/'+current+'/'+id+'.png?'+Date.now(),layer.color);
}
function updatePromptCount(){ $('promptCount').textContent=`Grid ${gridPoints.length} + ML ${mlPoints.length} + 수동 ${points.length}점 / box ${box?1:0}개`; }
function coord(e){let r=host.getBoundingClientRect(),s=fit*zoom;return [(e.clientX-r.left-panX)/s,(e.clientY-r.top-panY)/s]}
function sizeCanvas(){canvas.width=host.clientWidth;canvas.height=host.clientHeight;canvas.style.width=canvas.width+'px';canvas.style.height=canvas.height+'px';if(base.naturalWidth&&canvas.width&&canvas.height){fit=Math.min(canvas.width/base.width,canvas.height/base.height);panX=(canvas.width-base.width*fit*zoom)/2;panY=(canvas.height-base.height*fit*zoom)/2;}redraw()}
function rect(r,color){if(!r)return;ctx.strokeStyle=color;ctx.lineWidth=2/(fit*zoom);ctx.strokeRect(r[0],r[1],r[2]-r[0],r[3]-r[1])}
function normRect(r){return [Math.min(r[0],r[2]),Math.min(r[1],r[3]),Math.max(r[0],r[2]),Math.max(r[1],r[3])]}
function redraw(){ctx.clearRect(0,0,canvas.width,canvas.height);if(!base.complete||!base.naturalWidth)return;ctx.save();ctx.translate(panX,panY);ctx.scale(fit*zoom,fit*zoom);ctx.drawImage(activePage==='images'&&preprocessingPreview?preprocessingPreview:base,0,0);if($('showMasks').checked&&tint){ctx.save();ctx.globalAlpha=.5;ctx.drawImage(tint,0,0);ctx.restore()}if($('showMasks').checked&&showCov&&coverage.width){ctx.save();ctx.globalAlpha=.4;ctx.drawImage(coverage,0,0);ctx.restore()}
 const tpls=[state.preprocessing?.[current]?.auto_regions];if(state.legacy_templates_enabled)tpls.push(templateDraft||analysisRegionDraft||state.preprocessing?.[current]?.template);
 for(const t of tpls.filter(Boolean)){for(const k of ['scale_roi','scale_text_roi','sample_roi','magnification_roi'])if(t[k])rect(t[k].map((v,i)=>v*(i%2?base.height:base.width)),'#4ce3df');for(let q of t.text_rois||[])rect(q.map((v,i)=>v*(i%2?base.height:base.width)),'#ee7a8a')}
 if($('showPrompts').checked){rect(box,'#f5d65d');rect(roi,'#a479ff');}rect(scaleDraft,'#36e5e0');for(let r of textDraft)rect(r,'#ee7a8a');if(drag?.kind==='rect')rect(normRect([...drag.start,...drag.now]),'#fff');
 if($('showPrompts').checked){for(let [list,color] of [[gridPoints,'#4ce3df'],[mlPoints,'#bc8dff']]){ctx.fillStyle=color;for(let p of list){ctx.beginPath();ctx.arc(p[0],p[1],3/(fit*zoom),0,Math.PI*2);ctx.fill()}}
 for(let p of points){ctx.fillStyle=p[2]?'#20ff83':'#ff5471';ctx.beginPath();ctx.arc(p[0],p[1],5/(fit*zoom),0,Math.PI*2);ctx.fill()}
 }
 if(scaleBar)drawScaleLine(scaleBar);if(drag?.kind==='scale_line')drawScaleLine([drag.start,drag.now]);
 for(let s of ($('showMasks').checked?strokes:[])){ctx.beginPath();ctx.lineWidth=2*s.radius;ctx.strokeStyle=s.mode==='add'?'#39ef9c':'#fc6d83';ctx.globalAlpha=.6;s.points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.stroke();ctx.globalAlpha=1}
 ctx.restore()}
canvas.addEventListener('pointerdown',e=>{if(uiBusy||e.button!==0||!current||$('tool').value==='profile')return;canvas.setPointerCapture(e.pointerId);let p=coord(e),mode=$('tool').value;if(mode==='view'){drag={kind:'pan',start:[e.clientX,e.clientY],old:[panX,panY]}}else if(mode==='scale_line'){drag={kind:'scale_line',start:p,now:p}}else if(['scale','text','box','roi','scale_text_roi','sample_roi','magnification_roi'].includes(mode)){drag={kind:'rect',mode,start:p,now:p}}else if(mode.startsWith('brush')){activeStroke={mode:mode==='brush_add'?'add':'remove',radius:Number($('radius').value),points:[p]};strokes.push(activeStroke);drag={kind:'brush'}}else{if(p[0]>=0&&p[0]<base.width&&p[1]>=0&&p[1]<base.height){points.push([p[0],p[1],mode==='positive'?1:0]);updatePromptCount()}redraw()}});
canvas.addEventListener('pointermove',e=>{let p=coord(e);$('cursor').textContent=`좌표: ${p[0].toFixed(1)}, ${p[1].toFixed(1)} px`;if(!drag)return;if(drag.kind==='pan'){panX=drag.old[0]+e.clientX-drag.start[0];panY=drag.old[1]+e.clientY-drag.start[1]}if(drag.kind==='rect'||drag.kind==='scale_line')drag.now=p;if(drag.kind==='brush')activeStroke.points.push(p);redraw()});
canvas.addEventListener('pointerup',e=>{if(!drag)return;if(drag.kind==='scale_line')setScaleBar([drag.start,coord(e)].map(p=>[Math.max(0,Math.min(base.width,p[0])),Math.max(0,Math.min(base.height,p[1]))]));if(drag.kind==='rect'){let r=normRect([...drag.start,...coord(e)]);if(r[2]-r[0]>2&&r[3]-r[1]>2){if(drag.mode==='box')box=r;if(drag.mode==='roi')roi=r;if(drag.mode==='scale')scaleDraft=r;if(drag.mode==='text')textDraft.push(r);if(['scale_text_roi','sample_roi','magnification_roi'].includes(drag.mode)){templateDraft=currentTemplateDraft();templateDraft[drag.mode]=r.map((v,i)=>Math.max(0,Math.min(1,v/(i%2?base.height:base.width))))}}}drag=null;activeStroke=null;if(scaleDraft||textDraft.length)captureTemplateDraft();updatePromptCount();redraw()});
canvas.addEventListener('wheel',e=>{e.preventDefault();let [x,y]=coord(e),factor=e.deltaY<0?1.15:1/1.15;zoom=Math.max(.15,Math.min(12,zoom*factor));panX=e.offsetX-x*fit*zoom;panY=e.offsetY-y*fit*zoom;redraw()},{passive:false});
$('clearMarks').onclick=()=>{gridPoints=[];mlPoints=[];points=[];box=null;roi=null;strokes=[];updatePromptCount();redraw()};
$('zoomIn').onclick=()=>{zoom*=1.2;redraw()};$('zoomOut').onclick=()=>{zoom/=1.2;redraw()};$('resetView').onclick=()=>{if(base.naturalWidth){fit=Math.min(host.clientWidth/base.width,host.clientHeight/base.height);zoom=1;panX=(host.clientWidth-base.width*fit)/2;panY=(host.clientHeight-base.height*fit)/2;redraw()}};
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button,.page').forEach(x=>x.classList.remove('active'));b.classList.add('active');$(b.dataset.page).classList.add('active');activePage=b.dataset.page;redraw()});
$('upload').onchange=e=>task(async()=>{try{for(let f of e.target.files){let form=new FormData();form.append('file',f);let r=await fetch('/api/images',{method:'POST',body:form});if(!r.ok)throw Error(`${f.name}: ${await responseError(r)}`);current=(await r.json()).image_id}}finally{e.target.value='';await refresh()}});
async function deleteCurrentImage(){if(!current)return;if(!await confirmAction('현재 이미지와 해당 후보·스케일을 프로젝트에서 삭제할까요?'))return;const id=current;const result=await api('images/'+id,null,'DELETE');if(result.failed?.[id])throw Error(result.failed[id]);delete imageDrafts[id];loadedImage=null;current=null;await refresh()}
$('deleteImage').onclick=()=>task(deleteCurrentImage);$('deleteLoadedImage').onclick=()=>task(deleteCurrentImage);
$('clearLoadedImages').onclick=()=>task(async()=>{const count=Object.keys(state.images).length;if(!count)return;if(!await confirmAction(`${count}개 이미지와 모든 후보·스케일·검수 기록을 프로젝트에서 비울까요? 템플릿과 모델 설정은 유지됩니다.`))return;const result=await api('images',null,'DELETE');if(Object.keys(result.failed||{}).length){await refresh();throw Error('일부 이미지 삭제 실패: '+JSON.stringify(result.failed))}for(const id of Object.keys(imageDrafts))delete imageDrafts[id];loadedImage=null;current=null;points=[];gridPoints=[];mlPoints=[];box=null;roi=null;strokes=[];scaleBar=null;tint=null;preprocessingPreview=null;await refresh()});
$('imageSelect').onchange=e=>switchImage(e.target.value);$('candidateSelect').onchange=()=>task(async()=>{strokes=[];await loadMask()});$('layerSelect').onchange=()=>task(()=>loadLayer());$('showLayer').onclick=()=>task(()=>loadLayer());
$('templateSelect').onchange=e=>task(async()=>{await api('templates/select',{id:e.target.value});analysisRegionDraft=state.templates[e.target.value];templateDraft=null;scaleDraft=null;textDraft=[];await refresh();redraw()});
function currentTemplateDraft(){
 let previous=templateDraft||analysisRegionDraft||{...state.templates[state.selected_template],...(state.preprocessing?.[current]?.template||{})};
 let norm=r=>r.map((v,i)=>Math.max(0,Math.min(1,v/(i%2?base.height:base.width))));
 return {...previous,id:previous.id,name:$('templateName').value||previous.name,scale_roi:scaleDraft?norm(scaleDraft):previous.scale_roi,text_rois:[...previous.text_rois,...textDraft.map(norm)]};
}
async function storeTemplate(t){await api('templates',t);analysisRegionDraft=t;templateDraft=null;scaleDraft=null;textDraft=[];await refresh();redraw();say('템플릿 저장됨')}
$('saveTemplate').onclick=()=>task(()=>storeTemplate(currentTemplateDraft()));
$('newTemplate').onclick=()=>task(async()=>{let name=prompt('새 템플릿 이름','새 템플릿');if(!name?.trim())return;await storeTemplate({id:'tpl_'+Date.now(),name:name.trim(),scale_roi:null,text_rois:[]})});
$('copyTemplate').onclick=()=>task(async()=>{let t=currentTemplateDraft();let name=prompt('복사할 템플릿 이름',t.name+' 복사');if(!name?.trim())return;t.id='tpl_'+Date.now();t.name=name.trim();await storeTemplate(t)});
$('removeScale').onclick=()=>task(async()=>{let t=currentTemplateDraft();t.scale_roi=null;await storeTemplate(t)});
$('removeText').onclick=()=>task(async()=>{let t=currentTemplateDraft();t.text_rois=[];await storeTemplate(t)});
$('clearTemplate').onclick=()=>task(async()=>{let t=currentTemplateDraft();t.scale_roi=null;t.text_rois=[];for(const k of ['scale_text_roi','sample_roi','magnification_roi'])delete t[k];await storeTemplate(t)});
$('manualScale').onclick=()=>task(async()=>{if(!current||!scaleBar)throw Error('이미지와 스케일바 양 끝을 지정하세요');await api('scale/manual',{image_id:current,a:scaleBar[0],b:scaleBar[1],length:+$('scaleLength').value,unit:$('scaleUnit').value});await refresh();say('현재 이미지 스케일 저장 완료')});
$('autoScale').onclick=()=>task(async()=>{if(!current)throw Error('이미지를 선택하세요');let r=await api('scale/detect',{image_id:current,ocr_dir:$('ocrDir').value,language:'en'});await refresh();restoreScale();say(r.nm_per_px?'스케일 제안값과 바 위치를 확인하세요':'OCR 제안 실패. 바 검출과 실제 길이 입력을 사용하세요')});
$('confirmScale').onclick=()=>task(async()=>{await api('scale/confirm',{image_id:current});await refresh()});
$('loadModel').onclick=()=>task(async()=>{let r=await api('model/load',{checkpoint:$('checkpoint').value,variant:$('variant').value,device:$('device').value,decoder_path:$('decoder').value||null,refiner_path:$('refiner').value||null});await refresh();say('모델 로드: '+r.variant+' / '+r.device)});
$('automatic').onclick=()=>task(async()=>{if(!current)throw Error('이미지를 선택하세요');await ensureAnalysisRegions();let r=await api('prompts/grid',{image_id:current,grid:+$('grid').value});gridPoints=r.points;updatePromptCount();redraw();say('Grid 점 준비 완료. 추가점을 넣은 뒤 SAM 실행을 누르세요.')});
$('clearPrompts').onclick=()=>{points=[];gridPoints=[];mlPoints=[];box=null;updatePromptCount();redraw()};
function featurePromptConfig(){return {method:$('featureMethod').value||'kmeans',count:+$('mlCount').value,clusters:+$('mlClusters').value,min_distance:+$('mlDistance').value,denoise:$('promptDenoise').value||'none',sigma:+$('promptSigma').value||0,median_size:+$('promptMedian').value||3,range_sigma:+$('promptRange').value||.08,nlm_h:+$('promptNlm').value||10,canny_low:+$('cannyLow').value||0,canny_high:+$('cannyHigh').value||100,gradient_percentile:+$('gradientPercentile').value||75,edge_clearance:+$('edgeClearance').value||0,analysis_side:+$('featureAnalysisSide').value||512,profile_angle:$('profileAngle').value.trim()===''?null:+$('profileAngle').value,profile_scans:+$('profileScans').value||5,profile_min_width:+$('profileMinWidth').value||2,profile_max_width:+$('profileMaxWidth').value||80,profile_prominence:+$('profileProminence').value||4,profile_smooth:+$('profileSmooth').value||1}}
async function suggestFeatures(add){if(!current)throw Error('이미지를 선택하세요');await ensureAnalysisRegions();const id=current;const r=await api('prompts/ml',{image_id:id,existing:[...gridPoints,...mlPoints,...points.map(p=>p.slice(0,2))],...featurePromptConfig(),preview:true});if(id!==current)return;if(add){mlPoints.push(...r.points);updatePromptCount();redraw()}if(r.filtered_preview)$('featureFilteredPreview').src=r.filtered_preview;if(r.proposal_preview)$('featureProposalPreview').src=r.proposal_preview;$('featureInfo').textContent=`${r.method||'kmeans'} · ${r.count}개 ${add?'추가됨':'미리보기 (아직 추가 안 됨)'} · ${(r.warnings||[]).join(' ')}`;say($('featureInfo').textContent)}
$('suggestML').onclick=()=>task(()=>suggestFeatures(true));
$('previewFeatures').onclick=()=>task(()=>suggestFeatures(false));
$('clearFeaturePoints').onclick=()=>{mlPoints=[];updatePromptCount();redraw();$('featureInfo').textContent='추가점만 지웠습니다. Grid·수동점·box는 유지됩니다.'};
$('executeSAM').onclick=()=>task(async()=>{if(!current)throw Error('이미지를 선택하세요');await ensureAnalysisRegions();let r=await api('sam/prepared',{image_id:current,auto_points:[...gridPoints,...mlPoints],manual_points:points,box,manual_mode:$('manualMode').value,pred_iou:+$('pred').value,stability:+$('stability').value,nms:+$('nms').value});displayMode='candidate';await refresh();if(r.created.length){$('candidateSelect').value=r.created[0].id;await loadMask()}say(r.count+'개 후보 생성')});
canvas.addEventListener('contextmenu',e=>{e.preventDefault();let p=coord(e),best=null;for(let list of [points,gridPoints,mlPoints])list.forEach((q,i)=>{let d=Math.hypot(p[0]-q[0],p[1]-q[1]);if(d<12/(fit*zoom)&&(!best||d<best.d))best={list,i,d}});if(best){best.list.splice(best.i,1);updatePromptCount();redraw()}});
$('roiPrompt').onclick=()=>task(async()=>{if(!current||!selected())throw Error('후보를 선택하세요');await ensureAnalysisRegions();await roiEditor.open(current,selected(),base)});
$('independentROI').onclick=()=>task(async()=>{if(!current)throw Error('이미지를 선택하세요');await ensureAnalysisRegions();await roiEditor.open(current,null,base)});
$('duplicate').onclick=()=>task(async()=>{if(!selected())throw Error('후보를 선택하세요');let x=await api('candidates/duplicate',{image_id:current,candidate_id:selected()});await refresh();$('candidateSelect').value=x.id;await loadMask()});
$('applyBrush').onclick=()=>task(async()=>{if(!selected()||!strokes.length)throw Error('후보와 브러시 입력을 확인하세요');let x=await api('candidates/brush',{image_id:current,candidate_id:selected(),strokes});strokes=[];await refresh();$('candidateSelect').value=x.id;await loadMask()});
$('newLayer').onclick=()=>task(async()=>{const layer=await api('layers',{});await refresh();$('layerSelect').value=layer.id;say(layer.name+' 생성됨. 이름 수정 버튼으로 변경할 수 있습니다.')});
$('renameLayer').onclick=()=>task(async()=>{let id=+$('layerSelect').value;let name=prompt('레이어 이름',state.layers.find(x=>x.id===id)?.name);if(!name)return;await api('layers',{id,name});await refresh()});
$('deleteCandidate').onclick=()=>task(async()=>{let id=selected();if(!id)throw Error('후보를 선택하세요');if(!await confirmAction('후보 #'+id+'를 삭제할까요? 레이어에 연결되어 있으면 해당 mask도 표시에서 빠집니다.'))return;await api('candidates/'+current+'/'+id,null,'DELETE');strokes=[];await refresh()});
$('deleteLayer').onclick=()=>task(async()=>{let id=+$('layerSelect').value;if(!id)throw Error('레이어를 선택하세요');if(!await confirmAction('모든 이미지에서 이 레이어 지정을 해제하고 레이어를 삭제할까요? 후보 mask는 유지됩니다.'))return;await api('layers/'+id,null,'DELETE');await refresh()});
$('assign').onclick=()=>task(async()=>{if(!selected())throw Error('후보를 선택하세요');let x=await api('layers/assign',{image_id:current,candidate_id:selected(),layer_id:+$('layerSelect').value,instance_id:$('instance').value||null,reviewed:true});await refresh();$('candidateSelect').value=x.id;await loadMask()});
$('showCoverage').onclick=()=>task(async()=>{if(!current)throw Error('이미지를 선택하세요');let version=++overlayVersion;tint=null;let im=new Image();im.onload=()=>{if(version!==overlayVersion)return;let c=document.createElement('canvas');c.width=im.width;c.height=im.height;let x=c.getContext('2d');x.drawImage(im,0,0);let d=x.getImageData(0,0,c.width,c.height);for(let i=0;i<d.data.length;i+=4)d.data[i+3]=(d.data[i]||d.data[i+1]||d.data[i+2])?180:0;x.putImageData(d,0,0);coverage=c;showCov=true;redraw()};im.src='/api/coverage/'+current+'.png?'+Date.now();let x=await api('coverage/'+current+'/stats',null,'GET');$('coverageStats').textContent=`미분류 ${x.unassigned} px / 겹침 ${x.overlap} px / 제외 ${x.excluded} px`});


// Image browser: each image keeps its own scale and in-session prompt drafts.
async function switchImage(id){if(uiBusy||imageSwitchBusy||!id||id===current){$('imageSelect').value=current||'';return;}imageSwitchBusy=true;try{await task(async()=>{current=id;await refresh()})}finally{imageSwitchBusy=false}}
function renderGallery(){
 const ids=Object.keys(state.images),index=ids.indexOf(current),im=state.images[current];
 $('imagePosition').textContent=ids.length?`${index+1} / ${ids.length}`:'0 / 0';
 $('prevImage').disabled=index<=0;$('nextImage').disabled=index<0||index>=ids.length-1;
 $('imageMeta').textContent=im?`${im.name} · ${im.width} × ${im.height} px`:'';
 $('imageGallery').innerHTML=ids.map(id=>`<button data-image="${id}" class="${id===current?'selected':''}"><img loading="lazy" src="/api/thumbnails/${id}.jpg" alt="">${escapeHtml(state.images[id].name)}</button>`).join('');
}
$('imageGallery').onclick=e=>{const b=e.target.closest('[data-image]');if(b)switchImage(b.dataset.image)};
$('prevImage').onclick=()=>{let ids=Object.keys(state.images);return switchImage(ids[ids.indexOf(current)-1])};
$('nextImage').onclick=()=>{let ids=Object.keys(state.images);return switchImage(ids[ids.indexOf(current)+1])};
function candidateName(c){return c.name||c.source||`Mask ${c.id}`}
function sortedCandidates(){return [...(state.candidates[current]||[])].filter(c=>!c.deleted&&c.active!==false).sort((a,b)=>{
 let d=candidateSort.key==='name'?candidateName(a).localeCompare(candidateName(b),'ko',{numeric:true}):a[candidateSort.key]-b[candidateSort.key];return candidateSort.direction*(d||a.id-b.id);
})}
function renderCandidates(){
 $('candidateRows').innerHTML=sortedCandidates().map(c=>`<tr data-id="${c.id}" tabindex="0" aria-selected="${c.id===selected()}" class="${c.id===selected()?'selected':''}"><td>${c.id}</td><td>${escapeHtml(candidateName(c))}${c.layer_id?' → L'+c.layer_id:''}</td><td>${c.area.toLocaleString()}</td></tr>`).join('');
 for(let [id,key,label] of [['sortIndex','id','Index'],['sortName','name','Name'],['sortPixel','area','Pixel']])$(''+id).textContent=label+(candidateSort.key===key?(candidateSort.direction===1?' ↑':' ↓'):'');
 if(typeof window!=='undefined'&&window.dispatchEvent&&typeof CustomEvent!=='undefined')window.dispatchEvent(new CustomEvent('tem:candidates'));
}
function sortCandidates(key){candidateSort.direction=candidateSort.key===key?-candidateSort.direction:1;candidateSort.key=key;renderCandidates()}
$('sortIndex').onclick=()=>sortCandidates('id');$('sortName').onclick=()=>sortCandidates('name');$('sortPixel').onclick=()=>sortCandidates('area');
async function chooseCandidate(id){if(uiBusy)return;$('candidateSelect').value=id;strokes=[];await task(()=>loadMask())}
$('candidateRows').onclick=e=>{const row=e.target.closest('[data-id]');if(row)chooseCandidate(row.dataset.id)};
$('candidateRows').onkeydown=e=>{if(['Enter',' '].includes(e.key)){const row=e.target.closest('[data-id]');if(row){e.preventDefault();chooseCandidate(row.dataset.id)}}};
$('renameCandidate').onclick=()=>task(async()=>{const c=(state.candidates[current]||[]).find(c=>c.id===selected());if(!c)throw Error('후보를 선택하세요');let name=prompt('후보 이름',candidateName(c));if(!name?.trim())return;await api('candidates/name',{image_id:current,candidate_id:c.id,name});await refresh()});
$('showPrompts').onchange=redraw;$('showMasks').onchange=redraw;
function drawScaleLine(bar){ctx.save();ctx.strokeStyle='#ffb52c';ctx.fillStyle='#ffb52c';ctx.lineWidth=2/(fit*zoom);ctx.beginPath();ctx.moveTo(...bar[0]);ctx.lineTo(...bar[1]);ctx.stroke();for(const p of bar){ctx.beginPath();ctx.arc(...p,4/(fit*zoom),0,Math.PI*2);ctx.fill()}ctx.restore()}
function setScaleBar(bar){scaleBar=bar;for(let [i,id] of ['barX1','barY1','barX2','barY2'].entries())$(id).value=bar?Number(bar.flat()[i].toFixed(3)):'';updateScalePreview();redraw()}
function updateScalePreview(){
 const d=scaleBar?Math.hypot(scaleBar[1][0]-scaleBar[0][0],scaleBar[1][1]-scaleBar[0][1]):0,nm=+$('scaleLength').value*($('scaleUnit').value==='um'?1000:1);
 $('barPixels').textContent=d?`바 길이: ${d.toFixed(3)} px`:'바 길이: 미지정';
 $('scalePreview').textContent=d>=2&&nm>0?`계산 미리보기: ${(d/nm).toFixed(6)} px/nm · ${(nm/d).toFixed(6)} nm/px`:'';
}
function restoreScale(){const saved=state.scale[current],r=state.preprocessing?.[current];const s=['failed','error'].includes(r?.scale_status)?null:saved;barProposals=[];$('barSelect').innerHTML='<option value="">검출 전</option>';$('scaleLength').value=s?.length||'';$('scaleUnit').value=s?.unit==='um'||s?.unit==='µm'?'um':'nm';setScaleBar(s?.bar||null);if(s?.bar&&s.nm_per_px&&!s.length){$('scaleLength').value=s.nm_per_px*Math.hypot(s.bar[1][0]-s.bar[0][0],s.bar[1][1]-s.bar[0][1]);updateScalePreview()}}
$('scaleLength').oninput=updateScalePreview;$('scaleUnit').onchange=updateScalePreview;
for(const id of ['barX1','barY1','barX2','barY2'])$(id).oninput=()=>{const vals=['barX1','barY1','barX2','barY2'].map(id=>$(id).value);scaleBar=vals.every(v=>v!==''&&Number.isFinite(+v))?[[+vals[0],+vals[1]],[+vals[2],+vals[3]]]:null;updateScalePreview();redraw()};
$('drawScaleROI').onclick=()=>{if(!state.legacy_templates_enabled){say('위치 템플릿이 꺼져 있습니다. 자동 검출 또는 바 양 끝 직접 드래그를 사용하세요.');return}$('tool').value='scale';say('스케일바와 숫자가 포함된 영역을 드래그하세요.')};
$('drawScaleLine').onclick=()=>{$('tool').value='scale_line';say('스케일바의 한쪽 끝에서 반대쪽 끝까지 드래그하세요.')};
$('detectBar').onclick=()=>task(async()=>{if(!current)throw Error('이미지를 선택하세요');let r=await api('scale/bar',{image_id:current,roi:currentTemplateDraft().scale_roi});barProposals=r.candidates;$('barSelect').innerHTML=barProposals.map((b,i)=>`<option value="${i}">${i+1}: ${b.pixel_length} px · ${b.polarity==='bright'?'밝은 바':'어두운 바'}</option>`).join('');setScaleBar(barProposals[0]?.bar||null);say(barProposals.length?'주황색 선이 실제 바와 맞는지 확인하고 길이를 입력하세요.':'바를 찾지 못했습니다. 양 끝을 직접 드래그하세요.')});
$('barSelect').onchange=()=>setScaleBar(barProposals[+$('barSelect').value]?.bar||null);
function batchStatus(record){if(!record)return '미적용';if(record.scale_status==='failed'||record.scale_status==='error')return '검출·처리 실패';if(!record.regions_applied)return record.scale_requested?'스케일 설정 · 제외 미적용':'제외 미적용';return record.reviewed?'제외 검수 완료':'제외 검수 대기'}
function renderBatchResults(){
 const ids=Object.keys(state.images),records=state.preprocessing||{},applied=ids.filter(id=>records[id]?.regions_applied),reviewed=applied.filter(id=>records[id].reviewed),failed=ids.filter(id=>['failed','error'].includes(records[id]?.scale_status)),calibrated=ids.filter(id=>state.scale[id]?.confirmed&&state.scale[id]?.nm_per_px>0&&!['failed','error'].includes(records[id]?.scale_status));
 $('batchSummary').textContent=`전체 ${ids.length} · 제외 적용 ${applied.length} · 제외 검수 완료 ${reviewed.length} · 스케일 확정 ${calibrated.length} · 실패 ${failed.length}`;
 const rows=ids.map(id=>{const r=records[id],s=state.scale[id],bad=['failed','error'].includes(r?.scale_status),valid=s?.nm_per_px&&!bad,bar=s?.pixel_length||(s?.bar?Math.hypot(s.bar[1][0]-s.bar[0][0],s.bar[1][1]-s.bar[0][1]):null),tpl=r?.auto_regions||(state.legacy_templates_enabled?r?.template:null);
 return `<tr data-batch-image="${id}" tabindex="0" class="${id===current?'selected':''}"><td>${escapeHtml(state.images[id].name)}</td><td>${batchStatus(r)}${r?.bar_candidates?.length>1?' (복수 바 후보)':''}</td><td>${valid&&bar?bar.toFixed(2):'—'}</td><td>${valid&&s.length?s.length+' '+escapeHtml(s.unit||'nm'):'—'}</td><td>${valid?(1/s.nm_per_px).toFixed(6):'—'}</td><td>${valid?s.nm_per_px.toFixed(6):'—'}</td><td>${tpl?.scale_roi?1:0} / ${tpl?.text_rois?.length||0}</td><td>${r?.excluded_pixels||0}</td></tr>`}).join('');
 $('batchResults').innerHTML=rows;$('batchLargeRows').innerHTML=rows;
 const r=records[current];$('batchCurrentStatus').textContent=r?`${batchStatus(r)} · ${r.regions_applied?'제외 영역 적용됨':'제외 영역 미적용'}${r.last_error?' · '+r.last_error:''}`:'현재 이미지 미적용';
 $('batchConfirm').disabled=!r||r.reviewed;$('batchNext').disabled=!ids.some(id=>records[id]&&!records[id].reviewed);
}
async function loadPreprocessingPreview(){const token=++preprocessingVersion;preprocessingPreview=null;const mode=$('batchView').value||'overlay';if(!current||!state.preprocessing?.[current]||mode==='original'){redraw();return}const id=current;const im=await new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(Error('적용 결과 미리보기를 읽지 못했습니다.'));img.src=`/api/preprocessing/${id}/preview.png?mode=${mode}&v=${Date.now()}`});if(token===preprocessingVersion&&id===current){preprocessingPreview=im;redraw()}}
async function applyBatch(onlyCurrent){
 if(!current)throw Error('이미지를 먼저 로드하세요');
 const button=onlyCurrent?$('batchApplyCurrent'):$('batchApply');button.disabled=true;
 try{const result=await api('preprocessing/apply',{template:currentTemplateDraft(),image_ids:onlyCurrent?[current]:null,apply_regions:$('batchRegions').checked,apply_scale:$('batchScale').checked,length:+$('scaleLength').value||null,unit:$('scaleUnit').value});templateDraft=null;scaleDraft=null;textDraft=[];await refresh();restoreScale();say(`${result.count}개 이미지 적용 완료. 결과 목록에서 확인하세요.`)}finally{button.disabled=false}
}
$('batchApply').onclick=()=>task(()=>applyBatch(false));$('batchApplyCurrent').onclick=()=>task(()=>applyBatch(true));
function selectBatchRow(e){const row=e.target.closest('[data-batch-image]');if(row){$('batchTableDialog').close();return switchImage(row.dataset.batchImage)}}
$('batchResults').onclick=selectBatchRow;$('batchLargeRows').onclick=selectBatchRow;
$('openBatchTable').onclick=()=>$('batchTableDialog').showModal();$('closeBatchTable').onclick=()=>$('batchTableDialog').close();
$('batchView').onchange=()=>task(async()=>{renderBatchResults();await loadPreprocessingPreview()});
$('batchConfirm').onclick=()=>task(async()=>{if(!current)throw Error('이미지를 선택하세요');await api('preprocessing/confirm',{image_id:current});await refresh()});
$('batchNext').onclick=()=>{const ids=Object.keys(state.images),i=ids.indexOf(current),ordered=[...ids.slice(i+1),...ids.slice(0,i+1)],next=ordered.find(id=>state.preprocessing?.[id]&&!state.preprocessing[id].reviewed);if(next)return switchImage(next)};

function captureTemplateDraft(){templateDraft=currentTemplateDraft();analysisRegionDraft=templateDraft;pruneExcludedPrompts(templateDraft);scaleDraft=null;textDraft=[];renderRegionSummary()}
function renderRegionSummary(){if(!state.templates)return;const t=currentTemplateDraft();$('regionSummary').textContent=`일괄 적용할 영역: 스케일 ${t.scale_roi?1:0}개 + 글씨 제외 ${t.text_rois.length}개${templateDraft?' (저장 전 변경 포함)':''}`;$('regionList').innerHTML=[...(t.scale_roi?[`<li>스케일 ROI <button data-region="scale">제거</button></li>`]:[]),...t.text_rois.map((r,i)=>`<li>글씨 제외 ${i+1} <button data-region="${i}">제거</button></li>`)].join('')}
$('regionList').onclick=e=>{const b=e.target.closest('[data-region]');if(!b)return;const t=currentTemplateDraft();if(b.dataset.region==='scale')t.scale_roi=null;else t.text_rois.splice(+b.dataset.region,1);templateDraft=t;scaleDraft=null;textDraft=[];renderRegionSummary();redraw()};
const roiEditor=new ROIEditor({api,onSaved:async item=>{displayMode='candidate';await refresh();$('candidateSelect').value=item.id;await loadMask();say('재분할 후보 #'+item.id+' 저장됨')}});
new ResizeObserver(sizeCanvas).observe(host);const initialReady=refresh().then(()=>{if(typeof initializeV2==='function')return initializeV2()}).catch(e=>say(e.message));


function regionKey(t){return JSON.stringify([t?.scale_roi||null,t?.text_rois||[],t?.scale_text_roi||null,t?.sample_roi||null,t?.magnification_roi||null])}
function pruneExcludedPrompts(t){
 if(!base.width||!t)return;
 const rois=[t.scale_roi,...(t.text_rois||[]),t.scale_text_roi,t.sample_roi,t.magnification_roi].filter(Boolean);
 const allowed=p=>!rois.some(r=>p[0]>=Math.floor(r[0]*base.width)&&p[0]<Math.floor(r[2]*base.width)&&p[1]>=Math.floor(r[1]*base.height)&&p[1]<Math.floor(r[3]*base.height));
 gridPoints=gridPoints.filter(allowed);mlPoints=mlPoints.filter(allowed);points=points.filter(allowed);updatePromptCount();
}
async function ensureAnalysisRegions(){
 if(!current)throw Error('이미지를 선택하세요');
 const draft=(templateDraft||scaleDraft||textDraft.length)?currentTemplateDraft():analysisRegionDraft;
 if(state.legacy_templates_enabled&&draft&&regionKey(draft)!==regionKey(state.preprocessing?.[current]?.template)){
  const r=await api('preprocessing/apply',{template:draft,image_ids:[current],apply_regions:true,apply_scale:false,length:null,unit:'nm'});
  state.preprocessing=state.preprocessing||{};state.preprocessing[current]=r.results[current];
 }
 if(state.legacy_templates_enabled)pruneExcludedPrompts(draft||state.preprocessing?.[current]?.template);
 pruneExcludedPrompts(state.preprocessing?.[current]?.auto_regions);redraw();
}
