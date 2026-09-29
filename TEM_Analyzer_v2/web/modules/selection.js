/* Windows-style list selection and mask-to-layer drag/drop. */
export function mountSelection(T) {
  const $=id=>document.getElementById(id), selected=new Set();
  let owner=null,anchor=null,focus='masks',rectangle=null;
  const rows=$('candidateRows');
  function render(){
    if(owner!==T.current){selected.clear();owner=T.current;anchor=null}
    const ids=new Set(T.candidates().map(c=>c.id));
    for(const id of selected)if(!ids.has(id))selected.delete(id);
    for(const row of rows.querySelectorAll('[data-id]')){
      const on=selected.has(+row.dataset.id);row.classList.toggle('multi-selected',on);
      row.setAttribute('aria-selected',String(on));row.draggable=true;
    }
    $('maskSelectionCount').textContent=`${selected.size}개 선택 · Ctrl/Shift, Ctrl+A, Delete`;
  }
  function select(id,event){
    const ids=T.candidates().map(c=>c.id);
    if(event.shiftKey&&anchor!=null&&ids.includes(anchor)){
      if(!event.ctrlKey)selected.clear();
      const [a,b]=[ids.indexOf(anchor),ids.indexOf(id)].sort((x,y)=>x-y);
      ids.slice(a,b+1).forEach(x=>selected.add(x));
    }else{
      if(!event.ctrlKey&&!event.metaKey)selected.clear();
      if((event.ctrlKey||event.metaKey)&&selected.has(id))selected.delete(id);else selected.add(id);
      anchor=id;
    }
    render();
  }
  rows.onclick=e=>{
    if(T.busy)return;
    const row=e.target.closest('[data-id]');if(!row)return;
    select(+row.dataset.id,e);focus='masks';T.chooseCandidate(row.dataset.id);
  };
  rows.onkeydown=e=>{if(['Enter',' '].includes(e.key)){const r=e.target.closest('[data-id]');if(r){e.preventDefault();select(+r.dataset.id,e);T.chooseCandidate(r.dataset.id)}}};
  rows.addEventListener('dragstart',e=>{
    const row=e.target.closest('[data-id]');if(!row||T.busy){e.preventDefault();return}
    if(!selected.has(+row.dataset.id)){selected.clear();selected.add(+row.dataset.id);render()}
    e.dataTransfer.setData('application/x-tem-masks',JSON.stringify({image:T.current,ids:[...selected]}));
    e.dataTransfer.effectAllowed='move';
  });
  async function bulk(action,layer){
    const ids=selected.size?[...selected]:[T.selectedCandidate].filter(Boolean);
    if(action==='delete'&&!await T.confirm(`${ids.length}개 마스크를 삭제할까요? Undo로 복구할 수 있습니다.`))return;
    await T.api('workflow/masks/bulk',{image_id:T.current,candidate_ids:ids,action,layer_id:layer});
    if(action==='delete')selected.clear();await T.refresh();render();
  }
  for(const [id,action] of [['bulkAssign','assign'],['bulkUnassign','unassign'],['bulkDeleteMasks','delete'],['bulkReviewMasks','review']]){
    $(id).onclick=()=>T.task(()=>bulk(action,+$('layerSelect').value));
  }
  $('selectAllMasks').onclick=()=>{T.candidates().forEach(c=>selected.add(c.id));render()};
  $('layerDrops').addEventListener('dragover',e=>{if(e.target.closest('[data-drop-layer]')){e.preventDefault();e.dataTransfer.dropEffect='move'}});
  $('layerDrops').addEventListener('drop',e=>{
    const target=e.target.closest('[data-drop-layer]');if(!target)return;e.preventDefault();
    T.task(async()=>{const raw=e.dataTransfer.getData('application/x-tem-masks');if(!raw)throw Error('마스크 목록에서 드래그하세요');const data=JSON.parse(raw);if(data.image!==T.current)throw Error('이미지가 바뀌었습니다');
      await T.api('workflow/masks/bulk',{image_id:data.image,candidate_ids:data.ids,action:target.dataset.dropLayer?'assign':'unassign',layer_id:+target.dataset.dropLayer});await T.refresh();
    });
  });
  $('imageGallery').addEventListener('pointerdown',()=>focus='images');
  rows.addEventListener('pointerdown',()=>focus='masks');
  document.addEventListener('keydown',e=>{
    if(T.busy||e.target.closest('input,textarea,select,[contenteditable=true],dialog'))return;
    if(focus==='masks'&&(e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='a'){e.preventDefault();$('selectAllMasks').click()}
    if(e.key==='Delete'){e.preventDefault();(focus==='masks'?$('bulkDeleteMasks'):$('deleteSelected')).click()}
  });
  // Drag from empty space of the list to select a rectangle; row drag remains layer assignment.
  const scroll=rows.closest('.candidate-scroll');scroll.style.minHeight='130px';
  scroll.addEventListener('pointerdown',e=>{
    if(T.busy||e.button!==0||e.target.closest('tr,button'))return;
    rectangle={x:e.clientX,y:e.clientY,previous:e.ctrlKey?[...selected]:[]};e.preventDefault();
  });
  document.addEventListener('pointermove',e=>{
    if(!rectangle)return;selected.clear();rectangle.previous.forEach(x=>selected.add(x));
    const left=Math.min(rectangle.x,e.clientX),right=Math.max(rectangle.x,e.clientX),top=Math.min(rectangle.y,e.clientY),bottom=Math.max(rectangle.y,e.clientY);
    for(const r of rows.querySelectorAll('[data-id]')){const b=r.getBoundingClientRect();if(b.right>=left&&b.left<=right&&b.bottom>=top&&b.top<=bottom)selected.add(+r.dataset.id)}render();
  });
  document.addEventListener('pointerup',()=>rectangle=null);
  window.addEventListener('tem:candidates',render);window.addEventListener('tem:refreshed',render);
  return {render};
}
