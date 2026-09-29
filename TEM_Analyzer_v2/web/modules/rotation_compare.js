// Compare without replacing a saved alignment. Adoption is a separate preview.
export function mountRotationComparison(T,rotationConfig){
  const $=id=>document.getElementById(id),button=document.createElement('button');
  button.id='compareRotationMethods';button.textContent='회전 기준 비교 (자동 확정 안 함)';$('rotationPreview').before(button);
  const dialog=document.createElement('dialog');dialog.id='rotationMethodsDialog';
  dialog.innerHTML='<div class="dialog-heading"><h2>회전 기준 비교</h2><button id="closeRotationMethods">닫기</button></div><p id="rotationMethodsInfo"></p><div class="rotation-methods-scroll"><table><thead><tr><th>기준</th><th>보정각</th><th>잔차 px / 점 수</th><th>주의·실패</th><th>선택</th></tr></thead><tbody id="rotationMethodRows"></tbody></table></div><p>비교는 SAM을 다시 실행하거나 기존 회전/계측을 변경하지 않습니다. 작은 잔차·두 점의 직선·45° 근접은 물질 경계 정답이 아닙니다. 선택하면 미확정 회전으로 제안되며, 원본·회전 비교 후 따로 확정해야 합니다.</p>';
  document.body.append(dialog);$('closeRotationMethods').onclick=()=>dialog.close();
  const signature=()=>JSON.stringify([T.current,T.state.revision,rotationConfig()]);
  button.onclick=()=>T.task(async()=>{
    if(!T.current)throw Error('이미지를 선택하세요.');
    const iid=T.current,sig=signature(),config=rotationConfig();
    const result=await T.api('workflow/rotation/compare',{image_id:iid,config});
    if(signature()!==sig)throw Error('비교 중 입력이 바뀌었습니다. 다시 비교하세요.');
    $('rotationMethodsInfo').textContent=`${T.state.images[iid].name} · 방식 간 최대 각도 차이 ${result.max_angle_gap_deg.toFixed(3)}° · ${result.note}`;
    $('rotationMethodRows').innerHTML=result.rows.map((r,i)=>`<tr><td>${T.escape(r.name)}</td><td>${r.status==='proposed'?r.angle_deg.toFixed(4)+'°':'—'}</td><td>${r.status==='proposed'?(r.residual_px==null?'—':r.residual_px.toFixed(3))+' / '+(r.point_count||'—'):'—'}</td><td>${T.escape(r.error||(r.warnings||[]).join(' ')||'미확정 · 원본 영상 확인 필요')}</td><td>${r.status==='proposed'?`<button data-rotation-method="${i}">이 기준으로 미리보기</button>`:'실패'}</td></tr>`).join('');
    for(const b of $('rotationMethodRows').querySelectorAll('[data-rotation-method]')){
      b.onclick=()=>T.task(async()=>{
        if(signature()!==sig)throw Error('비교 후 입력이 바뀌었습니다. 닫고 다시 비교하세요.');
        const cfg=result.rows[+b.dataset.rotationMethod].config;
        await T.api('workflow/rotation/preview',{image_id:iid,config:cfg});
        $('rotationMode').value=cfg.mode;$('rotationEdge').value=cfg.edge||'top';
        $('rotationROI').value=cfg.roi?JSON.stringify(cfg.roi):'';$('rotationPoints').value=cfg.points?.length?JSON.stringify(cfg.points):'';
        dialog.close();await T.refresh();T.say('선택한 기준으로 미확정 회전을 제안했습니다. 원본·회전 비교 후 확정하세요.');
      });
    }
    dialog.showModal();
  });
  return {button,dialog,signature};
}
