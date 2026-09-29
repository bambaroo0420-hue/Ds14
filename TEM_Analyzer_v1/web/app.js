const $=id=>document.getElementById(id);
let state={},current=null,base=new Image(),mask=new Image(),coverage=new Image(),showCov=false,tint=null,points=[],box=null,roi=null,strokes=[],activeStroke=null,drag=null,scaleDraft=null,textDraft=[],zoom=1,panX=0,panY=0,fit=1;
let gridPoints=[],mlPoints=[],displayMode='candidate',overlayVersion=0,loadedImage=null;
const canvas=$('canvas'),ctx=canvas.getContext('2d'),host=$('canvasHost');
function say(msg){$('message').textContent=msg;$('message').style.display='block';setTimeout(()=>$('message').style.display='none',4500)}
async function api(path,body,method='POST') {const r=await fetch('/api/'+path,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});if(!r.ok){let x;try{x=await r.json()}catch{x={detail:r.statusText}}throw Error(x.detail||'요청 실패')}return r.headers.get('content-type')?.includes('application/json')?r.json():r}
async function task(fn){$('status').textContent='처리 중...';try{await fn();$('status').textContent='완료'}catch(e){say(e.message);$('status').textContent='오류: '+e.message}}
async function refresh(){
 const oldCandidate=$('candidateSelect').value,oldLayer=$('layerSelect').value;
 state=await api('state',null,'GET');
 $('imageSelect').innerHTML=Object.entries(state.images).map(([id,x])=>`<option value="${id}">${escapeHtml(x.name)}</option>`).join('');
 if(!current||!state.images[current])current=Object.keys(state.images)[0]||null;
 $('imageSelect').value=current||'';
 $('templateSelect').innerHTML=Object.values(state.templates).map(t=>`<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
 $('templateSelect').value=state.selected_template;$('templateName').value=state.templates[state.selected_template].name;
 $('layerSelect').innerHTML=state.layers.map(x=>`<option value="${x.id}">${escapeHtml(x.name)}</option>`).join('');
 if(state.layers.some(x=>String(x.id)===oldLayer))$('layerSelect').value=oldLayer;
 $('candidateSelect').innerHTML=(state.candidates[current]||[]).map(c=>`<option value="${c.id}">#${c.id} ${c.source} ${c.layer_id?'→ L'+c.layer_id:''} ${c.area}px</option>`).join('');
 if((state.candidates[current]||[]).some(c=>String(c.id)===oldCandidate))$('candidateSelect').value=oldCandidate;
 if(current!==loadedImage){points=[];gridPoints=[];mlPoints=[];box=null;roi=null;strokes=[];scaleDraft=null;textDraft=[];tint=null;showCov=false;overlayVersion++;await loadImage();}
 $('modelInfo').textContent=JSON.stringify(state.model||{status:'모델 미로드'},null,2);
 $('scaleInfo').textContent=state.scale[current]?.nm_per_px?`약 ${state.scale[current].nm_per_px.toFixed(5)} nm/px (${state.scale[current].confirmed?'확정':'제안·검수 필요'})`:'스케일 미확정';
 if(displayMode==='layer')await loadLayer();else await loadMask(false);
 updatePromptCount();redraw();
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
 if(changeMode)displayMode='candidate';
 let id=selected();let c=(state.candidates[current]||[]).find(x=>x.id===id);
 $('selectionInfo').textContent=c?`후보 #${id} / ${c.area}px / 예측 IoU ${c.predicted_iou==null?'수동 수정':c.predicted_iou.toFixed(3)}`:'선택된 후보 없음';
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
function sizeCanvas(){canvas.width=host.clientWidth;canvas.height=host.clientHeight;canvas.style.width=canvas.width+'px';canvas.style.height=canvas.height+'px';redraw()}
function rect(r,color){if(!r)return;ctx.strokeStyle=color;ctx.lineWidth=2/(fit*zoom);ctx.strokeRect(r[0],r[1],r[2]-r[0],r[3]-r[1])}
function normRect(r){return [Math.min(r[0],r[2]),Math.min(r[1],r[3]),Math.max(r[0],r[2]),Math.max(r[1],r[3])]}
function redraw(){ctx.clearRect(0,0,canvas.width,canvas.height);if(!base.complete||!base.naturalWidth)return;ctx.save();ctx.translate(panX,panY);ctx.scale(fit*zoom,fit*zoom);ctx.drawImage(base,0,0);if(tint){ctx.save();ctx.globalAlpha=.5;ctx.drawImage(tint,0,0);ctx.restore()}if(showCov&&coverage.width){ctx.save();ctx.globalAlpha=.4;ctx.drawImage(coverage,0,0);ctx.restore()}
 let t=state.templates?.[state.selected_template];if(t){if(t.scale_roi)rect(t.scale_roi.map((v,i)=>v*(i%2?base.height:base.width)),'#4ce3df');for(let q of t.text_rois)rect(q.map((v,i)=>v*(i%2?base.height:base.width)),'#ee7a8a')}
 rect(box,'#f5d65d');rect(roi,'#a479ff');rect(scaleDraft,'#36e5e0');for(let r of textDraft)rect(r,'#ee7a8a');if(drag?.kind==='rect')rect(normRect([...drag.start,...drag.now]),'#fff');
 for(let [list,color] of [[gridPoints,'#4ce3df'],[mlPoints,'#bc8dff']]){ctx.fillStyle=color;for(let p of list){ctx.beginPath();ctx.arc(p[0],p[1],3/(fit*zoom),0,Math.PI*2);ctx.fill()}}
 for(let p of points){ctx.fillStyle=p[2]?'#20ff83':'#ff5471';ctx.beginPath();ctx.arc(p[0],p[1],5/(fit*zoom),0,Math.PI*2);ctx.fill()}
 for(let s of strokes){ctx.beginPath();ctx.lineWidth=2*s.radius;ctx.strokeStyle=s.mode==='add'?'#39ef9c':'#fc6d83';ctx.globalAlpha=.6;s.points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.stroke();ctx.globalAlpha=1}
 ctx.restore()}
canvas.addEventListener('pointerdown',e=>{if(e.button!==0||!current)return;canvas.setPointerCapture(e.pointerId);let p=coord(e),mode=$('tool').value;if(mode==='view'){drag={kind:'pan',start:[e.clientX,e.clientY],old:[panX,panY]}}else if(['scale','text','box','roi'].includes(mode)){drag={kind:'rect',mode,start:p,now:p}}else if(mode.startsWith('brush')){activeStroke={mode:mode==='brush_add'?'add':'remove',radius:Number($('radius').value),points:[p]};strokes.push(activeStroke);drag={kind:'brush'}}else{if(p[0]>=0&&p[0]<base.width&&p[1]>=0&&p[1]<base.height){points.push([p[0],p[1],mode==='positive'?1:0]);updatePromptCount()}redraw()}});
canvas.addEventListener('pointermove',e=>{let p=coord(e);$('cursor').textContent=`좌표: ${p[0].toFixed(1)}, ${p[1].toFixed(1)} px`;if(!drag)return;if(drag.kind==='pan'){panX=drag.old[0]+e.clientX-drag.start[0];panY=drag.old[1]+e.clientY-drag.start[1]}if(drag.kind==='rect')drag.now=p;if(drag.kind==='brush')activeStroke.points.push(p);redraw()});
canvas.addEventListener('pointerup',e=>{if(!drag)return;if(drag.kind==='rect'){let r=normRect([...drag.start,...coord(e)]);if(r[2]-r[0]>2&&r[3]-r[1]>2){if(drag.mode==='box')box=r;if(drag.mode==='roi')roi=r;if(drag.mode==='scale')scaleDraft=r;if(drag.mode==='text')textDraft.push(r)}}drag=null;activeStroke=null;updatePromptCount();redraw()});
canvas.addEventListener('wheel',e=>{e.preventDefault();let [x,y]=coord(e),factor=e.deltaY<0?1.15:1/1.15;zoom=Math.max(.15,Math.min(12,zoom*factor));panX=e.offsetX-x*fit*zoom;panY=e.offsetY-y*fit*zoom;redraw()},{passive:false});
$('clearMarks').onclick=()=>{gridPoints=[];mlPoints=[];points=[];box=null;roi=null;strokes=[];textDraft=[];scaleDraft=null;updatePromptCount();redraw()};
$('zoomIn').onclick=()=>{zoom*=1.2;redraw()};$('zoomOut').onclick=()=>{zoom/=1.2;redraw()};$('resetView').onclick=()=>{if(base.naturalWidth){fit=Math.min(host.clientWidth/base.width,host.clientHeight/base.height);zoom=1;panX=(host.clientWidth-base.width*fit)/2;panY=(host.clientHeight-base.height*fit)/2;redraw()}};
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button,.page').forEach(x=>x.classList.remove('active'));b.classList.add('active');$(b.dataset.page).classList.add('active')});
$('upload').onchange=e=>task(async()=>{for(let f of e.target.files){let form=new FormData();form.append('file',f);let r=await fetch('/api/images',{method:'POST',body:form});if(!r.ok)throw Error((await r.json()).detail);current=(await r.json()).image_id}await refresh()});
$('deleteImage').onclick=()=>task(async()=>{if(!current)return;if(!confirm('현재 이미지와 해당 후보를 삭제할까요?'))return;await api('images/'+current,null,'DELETE');current=null;await refresh()});
$('imageSelect').onchange=e=>task(async()=>{current=e.target.value;await refresh()});$('candidateSelect').onchange=()=>task(async()=>{strokes=[];await loadMask()});$('layerSelect').onchange=()=>task(()=>loadLayer());$('showLayer').onclick=()=>task(()=>loadLayer());
$('templateSelect').onchange=e=>task(async()=>{await api('templates/select',{id:e.target.value});scaleDraft=null;textDraft=[];await refresh();redraw()});
function currentTemplateDraft(){
 let previous=state.templates[state.selected_template];
 let norm=r=>r.map((v,i)=>Math.max(0,Math.min(1,v/(i%2?base.height:base.width))));
 return {id:previous.id,name:$('templateName').value||previous.name,scale_roi:scaleDraft?norm(scaleDraft):previous.scale_roi,text_rois:[...previous.text_rois,...textDraft.map(norm)]};
}
async function storeTemplate(t){await api('templates',t);scaleDraft=null;textDraft=[];await refresh();redraw();say('템플릿 저장됨')}
$('saveTemplate').onclick=()=>task(()=>storeTemplate(currentTemplateDraft()));
$('newTemplate').onclick=()=>task(async()=>{let name=prompt('새 템플릿 이름','새 템플릿');if(!name?.trim())return;await storeTemplate({id:'tpl_'+Date.now(),name:name.trim(),scale_roi:null,text_rois:[]})});
$('copyTemplate').onclick=()=>task(async()=>{let t=currentTemplateDraft();let name=prompt('복사할 템플릿 이름',t.name+' 복사');if(!name?.trim())return;t.id='tpl_'+Date.now();t.name=name.trim();await storeTemplate(t)});
$('removeScale').onclick=()=>task(async()=>{let t=currentTemplateDraft();t.scale_roi=null;await storeTemplate(t)});
$('removeText').onclick=()=>task(async()=>{let t=currentTemplateDraft();t.text_rois=[];await storeTemplate(t)});
$('clearTemplate').onclick=()=>task(async()=>{let t=currentTemplateDraft();t.scale_roi=null;t.text_rois=[];await storeTemplate(t)});
$('manualScale').onclick=()=>task(async()=>{if(!current)throw Error('이미지를 선택하세요');let raw=prompt('스케일바: x1,y1,x2,y2,길이,단위(nm 또는 um)');if(!raw)return;let q=raw.split(',').map(x=>x.trim());if(q.length!==6)throw Error('6개 값을 입력하세요');await api('scale/manual',{image_id:current,a:[+q[0],+q[1]],b:[+q[2],+q[3]],length:+q[4],unit:q[5]});await refresh()});
$('autoScale').onclick=()=>task(async()=>{if(!current)throw Error('이미지를 선택하세요');let dir=prompt('로컬 EasyOCR 가중치 폴더','models/easyocr');if(!dir)return;let r=await api('scale/detect',{image_id:current,ocr_dir:dir,language:'en'});await refresh();say(r.nm_per_px?'스케일 제안값 확인 후 확정하세요':'스케일 검출 실패. 수동 입력을 사용하세요')});
$('confirmScale').onclick=()=>task(async()=>{await api('scale/confirm',{image_id:current});await refresh()});
$('loadModel').onclick=()=>task(async()=>{let r=await api('model/load',{checkpoint:$('checkpoint').value,variant:$('variant').value,device:$('device').value,decoder_path:$('decoder').value||null,refiner_path:$('refiner').value||null});await refresh();say('모델 로드: '+r.variant+' / '+r.device)});
$('automatic').onclick=()=>task(async()=>{if(!current)throw Error('이미지를 선택하세요');let r=await api('prompts/grid',{image_id:current,grid:+$('grid').value});gridPoints=r.points;updatePromptCount();redraw();say('Grid 점 준비 완료. 추가점을 넣은 뒤 SAM 실행을 누르세요.')});
$('clearPrompts').onclick=()=>{points=[];gridPoints=[];mlPoints=[];box=null;updatePromptCount();redraw()};
$('suggestML').onclick=()=>task(async()=>{if(!current)throw Error('이미지를 선택하세요');let r=await api('prompts/ml',{image_id:current,existing:[...gridPoints,...mlPoints,...points.map(p=>p.slice(0,2))],count:+$('mlCount').value,clusters:+$('mlClusters').value,min_distance:+$('mlDistance').value});mlPoints.push(...r.points);updatePromptCount();redraw();say(r.count+'개 ML 추가점 제안. 위치를 확인하세요.')});
$('executeSAM').onclick=()=>task(async()=>{if(!current)throw Error('이미지를 선택하세요');let r=await api('sam/prepared',{image_id:current,auto_points:[...gridPoints,...mlPoints],manual_points:points,box,manual_mode:$('manualMode').value,pred_iou:+$('pred').value,stability:+$('stability').value,nms:+$('nms').value});displayMode='candidate';await refresh();if(r.created.length){$('candidateSelect').value=r.created[0].id;await loadMask()}say(r.count+'개 후보 생성')});
canvas.addEventListener('contextmenu',e=>{e.preventDefault();let p=coord(e),best=null;for(let list of [points,gridPoints,mlPoints])list.forEach((q,i)=>{let d=Math.hypot(p[0]-q[0],p[1]-q[1]);if(d<12/(fit*zoom)&&(!best||d<best.d))best={list,i,d}});if(best){best.list.splice(best.i,1);updatePromptCount();redraw()}});
async function runPrompt(internal){if(!current)throw Error('이미지를 선택하세요');if(internal&&(!roi||!selected()))throw Error('후보와 내부 ROI를 선택하세요');let item=await api('sam/prompt',{image_id:current,points,box,roi:internal?roi:null,parent:internal?selected():null});await refresh();$('candidateSelect').value=item.id;await loadMask();say('후보 #'+item.id+' 저장됨')}
$('roiPrompt').onclick=()=>task(()=>runPrompt(true));
$('duplicate').onclick=()=>task(async()=>{if(!selected())throw Error('후보를 선택하세요');let x=await api('candidates/duplicate',{image_id:current,candidate_id:selected()});await refresh();$('candidateSelect').value=x.id;await loadMask()});
$('applyBrush').onclick=()=>task(async()=>{if(!selected()||!strokes.length)throw Error('후보와 브러시 입력을 확인하세요');let x=await api('candidates/brush',{image_id:current,candidate_id:selected(),strokes});strokes=[];await refresh();$('candidateSelect').value=x.id;await loadMask()});
$('newLayer').onclick=()=>task(async()=>{let name=prompt('새 레이어 이름');if(!name)return;await api('layers',{name});await refresh()});
$('renameLayer').onclick=()=>task(async()=>{let id=+$('layerSelect').value;let name=prompt('레이어 이름',state.layers.find(x=>x.id===id)?.name);if(!name)return;await api('layers',{id,name});await refresh()});
$('deleteCandidate').onclick=()=>task(async()=>{let id=selected();if(!id)throw Error('후보를 선택하세요');if(!confirm('후보 #'+id+'를 삭제할까요? 레이어에 연결되어 있으면 해당 mask도 표시에서 빠집니다.'))return;await api('candidates/'+current+'/'+id,null,'DELETE');strokes=[];await refresh()});
$('deleteLayer').onclick=()=>task(async()=>{let id=+$('layerSelect').value;if(!id)throw Error('레이어를 선택하세요');if(!confirm('모든 이미지에서 이 레이어 지정을 해제하고 레이어를 삭제할까요? 후보 mask는 유지됩니다.'))return;await api('layers/'+id,null,'DELETE');await refresh()});
$('assign').onclick=()=>task(async()=>{if(!selected())throw Error('후보를 선택하세요');let x=await api('layers/assign',{image_id:current,candidate_id:selected(),layer_id:+$('layerSelect').value,instance_id:$('instance').value||null,reviewed:true});await refresh();$('candidateSelect').value=x.id;await loadMask()});
$('showCoverage').onclick=()=>task(async()=>{if(!current)throw Error('이미지를 선택하세요');let version=++overlayVersion;tint=null;let im=new Image();im.onload=()=>{if(version!==overlayVersion)return;let c=document.createElement('canvas');c.width=im.width;c.height=im.height;let x=c.getContext('2d');x.drawImage(im,0,0);let d=x.getImageData(0,0,c.width,c.height);for(let i=0;i<d.data.length;i+=4)d.data[i+3]=(d.data[i]||d.data[i+1]||d.data[i+2])?180:0;x.putImageData(d,0,0);coverage=c;showCov=true;redraw()};im.src='/api/coverage/'+current+'.png?'+Date.now();let x=await api('coverage/'+current+'/stats',null,'GET');$('coverageStats').textContent=`미분류 ${x.unassigned} px / 겹침 ${x.overlap} px / 제외 ${x.excluded} px`});
new ResizeObserver(sizeCanvas).observe(host);refresh().catch(e=>say(e.message));
