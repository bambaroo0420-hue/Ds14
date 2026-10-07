/* Independent manual SAM objects with persistent drafts and Recipe v2. */
export function mountManualGroups(T){
  const $=id=>document.getElementById(id);let owner=null,groups=[],dirty=false;const drafts=new Map();
  const panel=document.createElement('details');panel.open=true;panel.innerHTML='<summary>Manual 1 / 2 / … 독립 객체</summary><p>캔버스에 한 객체의 +/−점·box를 만든 뒤 그룹에 추가하세요. 그룹마다 SAM을 별도로 실행합니다. 잠금은 그룹 입력 편집만 보호하며 실행은 허용합니다.</p><input id="manualGroupName" value="Manual 1" aria-label="Manual 그룹 이름"><label><input type="checkbox" id="groupUseROI">캔버스 ROI를 추론 제한으로 저장</label><button id="addManualGroup">현재 입력 → 새 그룹</button><select id="manualGroupSelect" aria-label="Manual 그룹 선택"></select><button id="loadManualGroup">선택 그룹 → 캔버스 편집</button><button id="replaceManualGroup">편집값으로 선택 그룹 갱신</button><button id="lockManualGroup">그룹 잠금/해제</button><button id="deleteManualGroup">그룹 삭제</button><button id="saveManualGroups" class="recipe-save">그룹 저장</button><label><input id="runManualGroups" type="checkbox" checked>준비한 SAM 실행에 위 그룹도 포함</label><p id="manualGroupsInfo"></p>';
  $('promptCount').closest('details').before(panel);
  const policy=document.createElement('label');policy.innerHTML='Recipe 자동점 정책 <select id="recipeAutoPolicy"><option value="reuse">저장 Grid/ML 좌표 그대로 재사용</option><option value="grid">대상별 Grid 재생성 + 수동 그룹</option><option value="features">대상별 ML/에지 재생성 + 수동 그룹</option><option value="grid_features">대상별 Grid+ML 재생성 + 수동 그룹</option></select>';
  $('savePromptPreset').before(policy);$('savePromptPreset').classList.add('recipe-save');$('savePromptPreset').textContent='점·box·Manual 그룹을 Recipe v2로 저장';
  const draft=T.promptDraft,setDraft=T.setPromptDraft;
  T.promptDraft=()=>({...draft(),manual_groups:structuredClone(groups),auto_policy:$('recipeAutoPolicy').value,grid:+$('grid').value});
  T.setPromptDraft=d=>{setDraft(d);groups=structuredClone(d.manual_groups||[]);$('recipeAutoPolicy').value=d.auto_policy||'reuse';if(d.grid!=null)$('grid').value=d.grid;
    const fields={method:'featureMethod',count:'mlCount',clusters:'mlClusters',min_distance:'mlDistance',denoise:'promptDenoise',sigma:'promptSigma',median_size:'promptMedian',range_sigma:'promptRange',nlm_h:'promptNlm',canny_low:'cannyLow',canny_high:'cannyHigh',gradient_percentile:'gradientPercentile',edge_clearance:'edgeClearance',analysis_side:'featureAnalysisSide',profile_angle:'profileAngle',profile_scans:'profileScans',profile_min_width:'profileMinWidth',profile_max_width:'profileMaxWidth',profile_prominence:'profileProminence',profile_smooth:'profileSmooth'};
    for(const [key,id] of Object.entries(fields))if(key in (d.feature_settings||{}))$(id).value=d.feature_settings[key]??'';
    owner=T.current;dirty=true;render()};
  function render(){
    if(owner!==T.current){if(owner&&dirty)drafts.set(owner,structuredClone(groups));owner=T.current;groups=structuredClone(drafts.get(owner)||T.state.manual_groups?.[owner]||[]);dirty=drafts.has(owner)}
    if(!dirty)groups=structuredClone(T.state.manual_groups?.[owner]||[]);
    const old=$('manualGroupSelect').value;$('manualGroupSelect').innerHTML=groups.map((g,i)=>`<option value="${i}">${T.escape(g.name)} ${g.locked?'🔒':''} · ${g.points.length}점 ${g.roi?'ROI':''}</option>`).join('');if(groups[+old])$('manualGroupSelect').value=old;
    $('manualGroupsInfo').textContent=`${groups.length}개 그룹 · ${dirty?'변경 미저장: 그룹 저장 또는 Recipe 저장 필요':'프로젝트 저장됨'} · 실행 후 마스크는 미배정 후보로 추가됩니다.`;
  }
  function fromCanvas(name){const d=T.manualDraft();if(!$('groupUseROI').checked)d.roi=null;if(!d.points.some(p=>p[2])&&!d.box)throw Error('양성점/box부터 지정하세요.');return {...d,name,locked:false}}
  function change(action){return ()=>T.task(async()=>{action();dirty=true;render()})}
  $('addManualGroup').onclick=change(()=>{const name=$('manualGroupName').value.trim();if(!name||groups.some(g=>g.name===name))throw Error('서로 다른 그룹 이름을 입력하세요.');groups.push(fromCanvas(name));T.setManualDraft({});$('manualGroupName').value='Manual '+(groups.length+1)});
  $('loadManualGroup').onclick=change(()=>{const g=groups[+$('manualGroupSelect').value];if(!g)throw Error('그룹이 없습니다.');T.setManualDraft(g);$('groupUseROI').checked=!!g.roi;T.say(g.locked?'잠긴 그룹입니다. 입력 변경은 저장되지 않습니다.':'점/box 편집 후 그룹 갱신을 누르세요.')});
  $('replaceManualGroup').onclick=change(()=>{const i=+$('manualGroupSelect').value,g=groups[i];if(!g||g.locked)throw Error('그룹을 선택하고 잠금을 해제하세요.');groups[i]=fromCanvas(g.name);T.setManualDraft({})});
  $('lockManualGroup').onclick=()=>T.task(async()=>{const g=groups[+$('manualGroupSelect').value];if(!g)throw Error('그룹이 없습니다.');g.locked=!g.locked;dirty=true;await save()});
  $('deleteManualGroup').onclick=change(()=>{const i=+$('manualGroupSelect').value;if(!groups[i]||groups[i].locked)throw Error('그룹을 선택하고 잠금을 해제하세요.');groups.splice(i,1)});
  async function save(){const r=await T.api('workbench/groups',{image_id:T.current,groups});groups=r.groups;dirty=false;drafts.delete(owner);await T.refresh();render()}
  $('saveManualGroups').onclick=()=>T.task(save);
  $('executeSAM').onclick=()=>T.task(async()=>{await T.ensureAnalysisRegions();const d=T.promptDraft();if(!$('runManualGroups').checked)d.manual_groups=[];const r=await T.api('sam/prepared',{image_id:T.current,...d,pred_iou:+$('pred').value,stability:+$('stability').value,nms:+$('nms').value});await T.refresh();T.say(`${r.count}개 후보 생성 · 레이어 배정은 별도입니다.`)});
  const capture=document.createElement('button');capture.id='roiToManualGroup';capture.className='recipe-save';capture.textContent='이 ROI·점·box를 새 Manual 그룹에 담기';$('roiRun').before(capture);
  capture.onclick=()=>{try{const editor=T.roiEditor;if(editor.busy)throw Error('ROI 작업 완료 후 저장하세요.');const d=JSON.parse(editor.signature());if(!d.points.some(p=>p[2])&&!d.box)throw Error('양성점/box가 필요합니다.');if(d.align_positive)throw Error('사전정렬 입력 Recipe는 아직 지원하지 않습니다. 사전정렬을 끄거나 별도 기록하세요.');const info=T.state.images[d.image_id];let n=1;while(groups.some(g=>g.name==='ROI Manual '+n))n++;groups.push({name:'ROI Manual '+n,points:d.points,box:d.box,roi:d.roi.map((v,i)=>v/(i%2?info.height:info.width)),locked:false,source_parent:d.parent});dirty=true;render();$('roiError').textContent='Manual 그룹에 담았습니다. 닫은 뒤 그룹/Recipe 저장을 누르세요. 부모 ID는 출처 기록이며 재사용 시 다른 영상의 부모를 추측하지 않습니다.'}catch(e){$('roiError').textContent=e.message}};
  window.addEventListener('tem:refreshed',render);render();
}
