/* Stable adapter for existing v2 views. New feature modules do not replace globals. */
window.TEM = {
  get state(){return state}, get current(){return current}, get busy(){return uiBusy},
  get selectedImages(){return [...imageSelection]}, get selectedCandidate(){return selected()},
  get boundaryROI(){return roi && base.width ? roi.map((v,i)=>v/(i%2?base.height:base.width)) : null},
  api, task, say, featurePromptConfig, escape:escapeHtml, download:downloadBlob,
  confirm(message){return new Promise(resolve=>{
    const dialog=document.createElement('dialog');dialog.id='confirmActionDialog';
    dialog.innerHTML='<h2>작업 확인</h2><p></p><button data-answer="no">취소</button><button data-answer="yes">확인 후 진행</button>';
    dialog.querySelector('p').textContent=message;
    let done=false;function finish(value){if(done)return;done=true;dialog.close();dialog.remove();resolve(value)}
    dialog.querySelector('[data-answer="yes"]').onclick=()=>finish(true);
    dialog.querySelector('[data-answer="no"]').onclick=()=>finish(false);
    dialog.addEventListener('cancel',e=>{e.preventDefault();finish(false)});
    document.body.append(dialog);dialog.showModal();
  })},
  refresh:()=>refresh(), switchImage, chooseCandidate,
  ask(title,value=''){return new Promise(resolve=>{
    const dialog=document.createElement('dialog');dialog.id='textInputDialog';
    dialog.innerHTML='<form><h2></h2><input aria-label="새 이름" maxlength="80"><button type="button">취소</button><button type="submit">저장</button></form>';
    dialog.querySelector('h2').textContent=title;dialog.querySelector('input').value=value||'';
    function finish(v){dialog.close();dialog.remove();resolve(v)}
    dialog.querySelector('form').onsubmit=e=>{e.preventDefault();finish(dialog.querySelector('input').value)};
    dialog.querySelector('button').onclick=()=>finish(null);dialog.oncancel=e=>{e.preventDefault();finish(null)};
    document.body.append(dialog);dialog.showModal();dialog.querySelector('input').focus();
  })},
  async showOverlay(url){const token=++overlayVersion;tint=null;showCov=false;redraw();const im=await new Promise((ok,no)=>{const image=new Image();image.onload=()=>ok(image);image.onerror=()=>no(Error('시각화 영상을 읽지 못했습니다.'));image.src=url});if(token!==overlayVersion)return;tint=im;redraw()},
  reloadOverlay:()=>loadMask(false), resizeCanvas:()=>sizeCanvas(),
  get rawROI(){return roi?[...roi]:null},
  get roiEditor(){return roiEditor},
  manualDraft(){return {points:points.map(p=>[...p]),box:box?[...box]:null,roi:this.boundaryROI}},
  setManualDraft(d){points=(d.points||[]).map(p=>[...p]);box=d.box?[...d.box]:null;roi=d.roi?d.roi.map((v,i)=>v*(i%2?base.height:base.width)):null;updatePromptCount();redraw()},
  promptDraft:()=>({auto_points:[...gridPoints,...mlPoints],manual_points:points.map(p=>[...p]),box:box?[...box]:null,manual_mode:document.getElementById('manualMode').value,feature_settings:featurePromptConfig()}),
  setPromptDraft(d){points=d.manual_points;gridPoints=d.auto_points;mlPoints=[];box=d.box;document.getElementById('manualMode').value=d.manual_mode;updatePromptCount();redraw()},
  candidates:()=>state.candidates?sortedCandidates():[],
  ensureAnalysisRegions,
  clearRegionDraft(){templateDraft=null;analysisRegionDraft=null;scaleDraft=null;textDraft=[];restoreScale()},
  resetImage(){return loadImage()},
};
