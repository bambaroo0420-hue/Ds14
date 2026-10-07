export function mountAnnotationReview(T){
  const $=id=>document.getElementById(id),panel=document.createElement('details');
  panel.innerHTML='<summary>놓친 문자 · 숫자/단위 박스 보완</summary><p>ROI를 그려 국소 대비·확대로 다시 OCR하거나, 숫자+단위+바를 모두 감싸는 박스를 직접 추가/교체하세요. 수동 박스는 제외 제안일 뿐 nm/px를 계산하지 않습니다.</p><button id="drawAnnotationROI">보완할 ROI 그리기</button><button id="retryAnnotationROI">ROI 대비·확대 OCR 재검출</button><label>수동 박스 종류 <select id="annotationBoxKind"><option value="text">일반 문자</option><option value="footer">하단 문자</option><option value="scale">숫자+단위+바</option><option value="magnification">배율</option></select></label><label>교체할 표 번호 (1부터, 빈 값: 추가)<input id="annotationBoxIndex" type="number" min="1"></label><button id="saveAnnotationBox">그린 ROI를 제외 제안 박스로 저장</button><p>그 후 표에서 제외할 행을 체크하고 “검출 박스를 제외 영역으로 적용”을 누르세요. 확정 축척은 변하지 않습니다. 근처 SAM이 왜곡되면 독립 ROI 분할로 문자 없는 영역을 별도 추론하세요. 원본 파일은 지우지 않습니다.</p>';
  $('annotationRows').closest('details').append(panel);
  $('drawAnnotationROI').onclick=()=>{$('tool').value='roi';$('tool').dispatchEvent(new Event('change'));T.say('중앙 원본 영상에 보완할 영역을 드래그하세요.')};
  function roi(){if(!T.boundaryROI)throw Error('먼저 ROI를 그리세요.');return T.boundaryROI}
  $('retryAnnotationROI').onclick=()=>T.task(async()=>{await T.api('workflow/annotations/detect',{image_id:T.current,retry_roi:roi(),ocr_dir:$('ocrDir').value});await T.refresh();T.say('국소 OCR 제안만 갱신했습니다. 표·박스를 확인하고 적용하세요.')});
  $('saveAnnotationBox').onclick=()=>T.task(async()=>{const v=$('annotationBoxIndex').value;await T.api('workflow/annotations/manual-box',{image_id:T.current,roi:roi(),kind:$('annotationBoxKind').value,region_index:v===''?null:+v-1});await T.refresh();T.say('제외 박스 제안만 저장했습니다. 표 확인 후 적용하세요.')});
}
