"""Read-only inspection of audit projects; writes only audit evidence artifacts."""
import hashlib
import html
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tem_analyzer.storage import Project
from tem_analyzer.labels import compose, UNKNOWN

OUT = ROOT / 'test-output/functional-audit-20261001'
GUI = Project(OUT / 'gui-project')
BOUNDARY = Project(ROOT / 'test-output/boundary-gui-audit-20261001/project')


def button_inventory():
    buttons = {}
    sources = [ROOT / 'web/index.html', *sorted((ROOT / 'web').rglob('*.js'))]
    for source in sources:
        text = source.read_text(encoding='utf-8')
        for match in re.finditer(r'<button\b([^>]*)>(.*?)</button>', text, re.S):
            attrs, label = match.groups()
            identity = re.search(r'\b(?:id|data-page)=["\']([^"\']+)["\']', attrs)
            if identity and '${' not in identity[1]:
                buttons[identity[1]] = dict(id=identity[1], label=html.unescape(re.sub('<[^>]+>', '', label)), source=str(source.relative_to(ROOT)))
    buttons['openAlignmentCompare'] = dict(id='openAlignmentCompare', label='원본 · 회전 결과 크게 비교', source='web/modules/metrology.js')
    buttons['compareRotationMethods'] = dict(id='compareRotationMethods', label='회전 기준 비교', source='web/modules/rotation_compare.js')
    for page in ('measure', 'batch'):
        for prefix, label in [('scopeShow', '선택 집합 전체 크게 보기'), ('scopeEdit', 'SAM 화면에서 선택 집합 편집')]:
            key=f'{prefix}_{page}'
            buttons[key]=dict(id=key,label=label,source='web/modules/scopes.js')
    passed = '''undo redo images sam boundary measure batch bulkAssign bulkUnassign lockLayer showLayer loadModel automatic previewFeatures suggestML savePromptPreset executeSAM independentROI roiRun roiAccept roiReset rotationPreview rotationConfirm compareRotationMethods openAlignmentCompare closeAlignmentCompare runMeasure scopeShow_measure closeScopeCompare startJob confirmSelectedRotations confirmSelectedScales detectAnnotations applyAnnotations batchConfirm inspectConflicts showCoverage layerBoundaryPreview layerBoundaryApply boundaryApply boundaryCancel profileTool clearConstraints annotate showLabels selectAllMasks bulkReviewMasks confirmGT duplicate deleteCandidate newLayer layerUp layerDown deleteLayer preparePromptBatch markPromptViewed confirmPromptBatch'''.split()
    passed += '''deleteImage restoreImage settings cancelJob retryJob saveMaskScope confirmMaskScope scopeEdit_measure saveFilter previewFilter originalFilter clearMarks clearPrompts sortPixel sortName sortIndex roiDiscard roiClear roiClose cancelCandidate applyBrush manualScale openBatchTable closeBatchTable closeRotationMethods'''.split()
    passed += '''prevImage nextImage deleteLoadedImage clearLoadedImages deleteSelected saveTemplate removeScale removeText clearTemplate batchApply batchApplyCurrent detectBar drawScaleLine confirmScale ocrBatch autoScale batchNext clearFeaturePoints editSAM assign evaluate previewPromptTransfer bulkDeleteMasks scopeShow_batch scopeEdit_batch closePromptBatch'''.split()
    partial = {
        'boundaryPreview':'기본 폭 12px 구조 보호 차단 → 3px에서 6px 변경 제안 성공',
        'addPin':'표시·개수 반영 확인; 고정점 포함 재추론/정확도는 미검증',
        'localStart':'구간 시작 저장 확인; 구간 적용 결과 정확도는 미검증',
        'localEnd':'부분 설정 1개 표시 확인; 구간 적용 결과 정확도는 미검증',
        'downloadResults':'버튼 완료; 브라우저 다운로드 이벤트 확인 시간초과. API ZIP 구조는 별도 통과',
        'exportGT':'버튼 완료; API ZIP/valid/semantic 별도 확인, 브라우저 저장파일 미확인',
        'roiPrompt':'부모 내부 실제 SAM 28,005px 미리보기와 취소 확인; 이번 GUI에서는 저장하지 않음',
        'toggleLegacyTemplates':'켬/끔 상태 확인; 고정 박스 일괄 적용은 미실행',
        'drawScaleROI':'템플릿 비활성 안내 확인; 실제 ROI 드래그/바 검출은 미실행',
        'zoomIn':'버튼 입력 오류 없음; 전후 배율 수치/화면 비교 미완료',
        'zoomOut':'버튼 입력 오류 없음; 전후 배율 수치/화면 비교 미완료',
        'resetView':'버튼 입력 오류 없음; 다양한 확대·이동 후 초기화 범위 미검증',
        'matchLayers':'미검수 기준 이미지 차단 오류 확인; 유효 기준의 대응 성공은 이번 GUI에서 미검증',
        'exportBatch':'CD 만료 결과 차단 확인, 재측정 후 API 두 축 ZIP 확인; 브라우저 파일 저장 미확인',
        'evaluateCSV':'버튼 완료, 브라우저 다운로드 파일 자체는 미확인',
    }
    partial['drawScaleROI']='실제 ROI 드래그·템플릿 저장·현재/전체 적용 확인. 바가 없는 합성 영상의 ROI; 실제 바 검출은 다른 19 영상에서 별도 확인'
    failures = {key:'앱 내 브라우저 prompt() 미지원 오류' for key in ('renameLayer','renameCandidate','newTemplate','copyTemplate')}
    failures['rotationUseROI']='입력 도구에 roi 항목 없음. 버튼은 null을 입력; ROI 편집기 this.roi와 메인 roi가 별개'
    api = set()
    for key, item in buttons.items():
        item['status'] = '직접 GUI 실행 확인' if key in passed else '미실행'
        item['note']='제한된 시험 조건. 모든 입력 조합/과학적 정확도 보장이 아님' if key in passed else '코드 존재만으로 정상 판정하지 않음'
        if key in api:
            item.update(status='API/회귀 시험만', note='이번 실제 GUI 버튼 성공으로 세지 않음')
        if key in partial:
            item.update(status='부분 확인/조건부', note=partial[key])
        if key in failures:
            item.update(status='재현 실패',note=failures[key])
    return list(buttons.values())


report = {'contract':'Audit of existing v2.2.9; no production code fixes; GUI/API evidence separated.'}
manifest = json.loads((ROOT / 'SOURCE_SHA256.json').read_text(encoding='utf-8'))
changed=[]
for name,digest in manifest.items():
    path=ROOT/name
    if not path.exists():
        changed.append({'file':name,'reason':'missing'});continue
    raw=path.read_bytes()
    if digest not in (hashlib.sha256(raw).hexdigest(),hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()):
        changed.append({'file':name,'reason':'hash mismatch'})
report['manifest']={'files':len(manifest),'differences':changed}
report['gui_candidates']={iid:[{k:c.get(k) for k in ('id','source','area','layer_id','prompts','reviewed','active','deleted')} for c in cs if not c.get('deleted') and c.get('active',True)] for iid,cs in GUI.state['candidates'].items()}
report['gui_recipe']=GUI.state.get('prompt_presets',{})
report['gui_transfers']=GUI.state.get('prompt_transfers',{})
report['gui_jobs']=GUI.state.get('jobs',{})
try:
    request=urllib.request.Request('http://127.0.0.1:8894/api/workflow/export',data=json.dumps(dict(image_ids=list(GUI.state['images']),scope_id='target',include_gt=False,export_all_axes=True)).encode(),headers={'Content-Type':'application/json'},method='POST')
    batch_bytes=urllib.request.urlopen(request,timeout=20).read()
    (OUT/'gui-final-both-axes-api.zip').write_bytes(batch_bytes)
    with zipfile.ZipFile(io.BytesIO(batch_bytes)) as archive:
        report['gui_batch_zip_entries']=archive.namelist()
        report['gui_batch_zip_all_axes']=all(f'{iid}/measurements/{axis}.json' in archive.namelist() for iid in GUI.state['images'] for axis in ('thickness','cd'))
except Exception as exc:
    report['gui_batch_export_error']=str(exc)
report['gui_rotations']={iid:{k:r.get(k) for k in ('config','transform','fit','confirmed','warnings')} for iid,r in GUI.state.get('alignments',{}).items()}
report['gui_scope']=GUI.state.get('mask_scopes',{})
report['gui_original_candidate_3_area']=GUI.candidate('6615e5fea014',3)['area']
report['gui_brush_candidates']=[{k:c.get(k) for k in ('id','area','parent','active','deleted')} for c in GUI.state['candidates']['6615e5fea014'] if c['source']=='brush-preview']
report['boundary_gui_jobs']=BOUNDARY.state.get('jobs',{})
report['gui_measurements']={iid:{axis:{k:m.get(k) for k in ('summary','sampling','scope_id','review_status')} for axis,m in axes.items()} for iid,axes in GUI.state.get('measurements_by_axis',{}).items()}
iid='6615e5fea014';old_ids=[3,4,5];new_ids=[c['id'] for c in GUI.state['candidates'][iid] if c['source'].startswith('transferred-')]
report['gui_ecc_best_iou']={str(cid):max((float((GUI.mask(iid,cid)&GUI.mask(iid,n)).sum()/max(1,(GUI.mask(iid,cid)|GUI.mask(iid,n)).sum())) for n in new_ids),default=None) for cid in old_ids}
bid=next(iter(BOUNDARY.state['images']));cs=[c for c in BOUNDARY.state['candidates'][bid] if c.get('active',True) and not c.get('deleted') and c.get('layer_id')]
am=BOUNDARY.mask(bid,next(c['id'] for c in cs if c['layer_id']==1));bm=BOUNDARY.mask(bid,next(c['id'] for c in cs if c['layer_id']==2))
labels,valid,conflict=compose(BOUNDARY,bid)
edge=np.array([np.flatnonzero(am[:,x])[-1] for x in range(30,450)])
report['boundary']={'synthetic':True,'overlap_pixels':int((am&bm).sum()),'union_pixels':int((am|bm).sum()),'initial_union_pixels':100800,'background_pixels':int((labels==0).sum()),'unknown_pixels':int((labels==UNKNOWN).sum()),'valid_pixels':int(valid.sum()),'edge_abs_error_to_last_true_row_149':{'mean':float(np.abs(edge-149).mean()),'median':float(np.median(np.abs(edge-149))),'max':float(np.abs(edge-149).max())}}
try:
    data=urllib.request.urlopen(f'http://127.0.0.1:8895/api/v2/export/{bid}.zip',timeout=15).read()
    (OUT/'gui-boundary-gt-api.zip').write_bytes(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        report['boundary']['api_zip_entries']=z.namelist()
        exported=np.asarray(Image.open(io.BytesIO(z.read('valid.png'))))>0
        report['boundary']['export_valid_equals_compose']=bool(np.array_equal(exported,valid))
        reviewed_labels, reviewed_valid, _ = compose(BOUNDARY,bid,reviewed_only=True)
        report['boundary']['export_valid_equals_reviewed_contract']=bool(np.array_equal(exported,reviewed_valid))
        report['boundary']['exported_valid_pixels']=int(exported.sum())
except Exception as exc:
    report['boundary']['export_error']=str(exc)
buttons=button_inventory();report['button_inventory']=buttons
report['button_counts']={status:sum(x['status']==status for x in buttons) for status in sorted({x['status'] for x in buttons})}
(OUT/'gui-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# 버튼별 실행 감사 (2026-10-01)','', '정적 HTML/JS의 명명된 버튼 목록 + 알려진 동적 버튼. 반복 이미지/후보 행, summary, checkbox/select, 동적 확인창 버튼은 별도 시나리오로 검토한다. 이 목록을 전체 조작 완료율로 해석하지 않는다.','', '| ID | 버튼 | 확인 수준 | 결과/남은 범위 |','|---|---|---|---|']
for b in buttons:
    lines.append('| '+ ' | '.join(str(b[k]).replace('|','/').replace('\n',' ') for k in ('id','label','status','note'))+' |')
(OUT/'BUTTON_AUDIT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
# Scientific contact sheet: controlled augmentations, no generative editing.
augment=ROOT/'test-output/augment-audit-20261001'
names=['baseline','brightness_065','noise_sigma12','shift_22_minus9','resize_120pct','stretch_x125_y090','rotate12_same_frame']
sheet=Image.new('RGB',(1400,820),'#16212a');draw=ImageDraw.Draw(sheet)
for index,name in enumerate(names):
    image=Image.open(augment/f'{name}_normalized_overlay.png').convert('RGB');image.thumbnail((310,335))
    x=20+(index%4)*345;y=40+(index//4)*390
    sheet.paste(image,(x,y));draw.text((x,y-22),name,fill='white')
draw.text((20,805),'Real SAM outputs; green = predicted mask. Previous SAM consistency is not expert GT accuracy.',fill='white')
sheet.save(OUT/'19-augmentation-contact-sheet.png')
print(json.dumps({k:report[k] for k in ('manifest','button_counts','gui_ecc_best_iou','boundary')},ensure_ascii=False,indent=2))
