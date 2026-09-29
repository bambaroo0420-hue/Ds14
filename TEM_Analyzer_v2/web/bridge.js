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
  promptDraft:()=>({auto_points:[...gridPoints,...mlPoints],manual_points:points.map(p=>[...p]),box:box?[...box]:null,manual_mode:document.getElementById('manualMode').value,feature_settings:featurePromptConfig()}),
  setPromptDraft(d){points=d.manual_points;gridPoints=d.auto_points;mlPoints=[];box=d.box;document.getElementById('manualMode').value=d.manual_mode;updatePromptCount();redraw()},
  candidates:()=>sortedCandidates(),
  clearRegionDraft(){templateDraft=null;analysisRegionDraft=null;scaleDraft=null;textDraft=[];restoreScale()},
  resetImage(){return loadImage()},
};
