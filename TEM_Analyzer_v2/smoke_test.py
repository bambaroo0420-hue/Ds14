"""Offline, synthetic end-to-end check for the TEM Analyzer server and optional SAM.

No company image is read or transmitted. The in-process API uses a temporary project.
"""
import argparse
import importlib
import io
import json
import os
import sys
import tempfile
import time
from urllib.request import urlopen

import numpy as np
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient


def synthetic_png():
    image = Image.new('RGB', (256, 192), '#22272d')
    draw = ImageDraw.Draw(image)
    draw.rectangle((22, 22, 233, 53), fill='#949a9c')
    draw.rectangle((22, 54, 233, 101), fill='#565f68')
    draw.rectangle((22, 102, 233, 151), fill='#c9c6bd')
    draw.rectangle((22, 152, 233, 171), fill='#50535a')
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


def request(client, method, path, **kwargs):
    r = client.request(method, path, **kwargs)
    if r.status_code >= 400:
        raise RuntimeError(f'{method} {path}: HTTP {r.status_code}: {r.text[:350]}')
    return r.json() if 'application/json' in r.headers.get('content-type', '') else r


def run(args):
    results = []
    def check(name, action):
        start = time.perf_counter()
        value = action()
        results.append({'step': name, 'status': 'PASS', 'seconds': round(time.perf_counter()-start, 3)})
        print(f'[PASS] {name} ({results[-1]["seconds"]} s)', flush=True)
        return value

    if args.url:
        def check_remote():
            base = args.url.rstrip('/')
            with urlopen(base + '/api/state', timeout=10) as response:
                state = json.load(response)
            if 'schema_version' not in state:
                raise AssertionError('원격 API 응답이 올바르지 않습니다.')
            with urlopen(base + '/', timeout=10) as response:
                if response.status != 200: raise AssertionError('UI 접속 실패')
            return state
        check('VS Code 전달 주소의 웹 UI와 API 접속', check_remote)

    with tempfile.TemporaryDirectory(prefix='tem_analyzer_smoke_') as directory:
        os.environ['TEM_PROJECT_DIR'] = directory
        import tem_analyzer.api as api
        api = importlib.reload(api)
        client = TestClient(api.app)
        check('웹 UI 접속', lambda: request(client, 'GET', '/'))
        data = synthetic_png()
        image_id = check('합성 이미지 업로드', lambda: request(client, 'POST', '/api/images', files={'file': ('synthetic.png', data, 'image/png')})['image_id'])
        check('템플릿 저장', lambda: request(client, 'POST', '/api/templates', json={'id':'smoke','name':'테스트','scale_roi':[0,.82,.35,.98],'text_rois':[[.75,0,.99,.1]]}))
        scale = check('수동 스케일 설정', lambda: request(client, 'POST', '/api/scale/manual', json={'image_id':image_id,'a':[20,170],'b':[120,170],'length':50,'unit':'nm'}))
        if abs(scale['nm_per_px'] - .5)>1e-9: raise AssertionError('nm/px 계산 오류')

        if args.checkpoint:
            model = check('SAM 체크포인트 로드', lambda: request(client, 'POST', '/api/model/load', json={'checkpoint':args.checkpoint,'variant':args.variant,'device':args.device,'decoder_path':args.decoder,'adaptation_path':args.adaptation}))
            print(f'  {model["variant"]} / {model["device"]}', flush=True)
            candidate = check('양성점 + box 추론', lambda: request(client,'POST','/api/sam/prompt',json={'image_id':image_id,'points':[[128,76,1]],'box':[25,56,230,99]}))
            if not 0<candidate['area']<256*192:raise AssertionError('점/box 마스크 면적이 비정상입니다.')
            check('ROI 내부 재분할', lambda: request(client,'POST','/api/sam/prompt',json={'image_id':image_id,'points':[[128,76,1]],'roi':[50,55,195,102],'parent':candidate['id']}))
            if not args.no_grid:
                grid = check(f'grid {args.grid} 자동 후보', lambda: request(client,'POST','/api/sam/automatic',json={'image_id':image_id,'grid':args.grid,'pred_iou':args.pred_iou,'stability':args.stability,'nms':args.nms}))
                print(f'  필터 통과 후보 {grid["count"]}개 (0개도 API 성공일 수 있음)',flush=True)
        else:
            # The storage and UI workflow can be checked without torch or a checkpoint.
            mask = np.zeros((192,256), dtype=bool);mask[60:95,30:220] = True
            candidate = check('테스트 마스크 저장', lambda: api.project.put_candidate(image_id,mask,'synthetic-test'))

        duplicate = check('후보 복제',lambda:request(client,'POST','/api/candidates/duplicate',json={'image_id':image_id,'candidate_id':candidate['id']}))
        edited = check('브러시 보정',lambda:request(client,'POST','/api/candidates/brush',json={'image_id':image_id,'candidate_id':duplicate['id'],'strokes':[{'mode':'remove','radius':5,'points':[[128,76]]}]}))
        check('레이어/instance 지정',lambda:request(client,'POST','/api/layers/assign',json={'image_id':image_id,'candidate_id':edited['id'],'layer_id':1,'instance_id':'cell_1','reviewed':True}))
        stats = check('겹침·미분류 검수',lambda:request(client,'GET',f'/api/coverage/{image_id}/stats'))
        check('저장 후 재로드', lambda: validate_restart(directory,image_id,edited['id']))
        print('  검수 픽셀:',stats,flush=True)
        print('  테스트 데이터는 임시 폴더와 함께 삭제됩니다.',flush=True)
    return results


def validate_restart(directory,image_id,candidate_id):
    from tem_analyzer.storage import Project
    p=Project(directory)
    if p.candidate(image_id,candidate_id)['instance_id'] != 'cell_1':raise AssertionError('레이어가 복원되지 않았습니다.')
    if not p.mask(image_id,candidate_id).any():raise AssertionError('마스크가 복원되지 않았습니다.')
    return True


def main():
    p=argparse.ArgumentParser(description='Synthetic TEM Analyzer smoke test; does not read company images.')
    p.add_argument('--url',help='VS Code Ports 탭의 Forwarded Address (접속 확인만)')
    p.add_argument('--checkpoint',help='SAM 가중치 경로. 생략하면 모델 추론 없이 앱 기능 검사')
    p.add_argument('--variant',choices=['vit_h','vit_l','vit_b'],default='vit_h')
    p.add_argument('--device',choices=['auto','cuda','cpu'],default='auto')
    p.add_argument('--decoder',help='동일 SAM 구조 mask_decoder state_dict 경로')
    p.add_argument('--adaptation',help='TEM SAM Lab adaptation.pt 경로')
    p.add_argument('--grid',type=int,default=2,help='테스트 grid 한 변의 점 수 (기본 2)')
    p.add_argument('--no-grid',action='store_true',help='자동 grid 추론 생략')
    p.add_argument('--pred-iou',type=float,default=.5)
    p.add_argument('--stability',type=float,default=.5)
    p.add_argument('--nms',type=float,default=.8)
    args=p.parse_args()
    if not 2<=args.grid<=32:p.error('grid는 2~32입니다.')
    try:
        steps=run(args)
        print(f'완료: {len(steps)}개 항목 통과',flush=True)
        return 0
    except Exception as exc:
        print(f'[FAIL] {exc.__class__.__name__}: {exc}',file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':raise SystemExit(main())

