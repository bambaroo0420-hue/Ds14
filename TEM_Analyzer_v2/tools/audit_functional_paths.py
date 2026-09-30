"""Actual-model integration audit; clone known test project, never edit the source.

Run once per fresh --output folder. No production application changes or mocked
SAM results. Pipeline confirmations are test-only, not expert GT acceptance.
"""
import argparse
import asyncio
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import time
import zipfile

import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main(args):
    source = Path(args.source).resolve()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    hashes = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source.rglob('*') if p.is_file()}
    shutil.copytree(source, out / 'project')
    shutil.copytree(source, out / 'gui-project')
    os.environ['TEM_PROJECT_DIR'] = str(out / 'project')
    import torch
    torch.set_num_threads(4)
    import tem_analyzer.api as api
    from tem_analyzer.storage import Project
    from tem_analyzer.services.prompt_batches import transfer_signature, current_transfer
    p = api.project
    report = dict(contract='Actual SAM + HTTP/API + disk reload; no expert GT claims; source preserved.', checks=[], jobs=[])

    def record(name, ok, **detail):
        value = dict(name=name, passed=bool(ok), **detail)
        report['checks'].append(value)
        (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(value, ensure_ascii=True), flush=True)

    with TestClient(api.app) as client:
        def post(path, body, status=200):
            response = client.post('/api/' + path, json=body)
            if response.status_code != status:
                raise AssertionError(f'{path}: {response.status_code}: {response.text[:500]}')
            return response.json() if 'json' in response.headers.get('content-type', '') else response

        async def job(name, image_ids, steps, settings):
            before = {iid: len(p.state['candidates'][iid]) for iid in image_ids}
            started = time.perf_counter()
            manager = api.app.state.workflow_jobs
            manager.start(image_ids, steps, settings)
            await manager.task
            result = copy.deepcopy(manager.current)
            report['jobs'].append(result)
            record(name, result['status'] == 'completed', seconds=round(time.perf_counter()-started, 3),
                   status=result['status'], rows=result['rows'],
                   candidates_added={iid:len(p.state['candidates'][iid])-before[iid] for iid in image_ids})
            return result

        source_iid = '8d0ab21d53e9'
        target_iid = '588fd610cbc0'
        gui_iid = '36b757a5e849'
        original_ids = [6, 8]
        original_masks = {cid: p.mask(gui_iid, cid).copy() for cid in original_ids}
        bulk = dict(image_id=gui_iid, candidate_ids=original_ids)
        post('workflow/masks/bulk', dict(bulk, action='assign', layer_id=1))
        record('bulk_assign_reload', all(Project(p.root).candidate(gui_iid,n)['layer_id']==1 for n in original_ids))
        post('v2/lock', dict(layer_id=1, locked=True))
        before = copy.deepcopy(p.state)
        blocked = post('workflow/masks/bulk', dict(bulk, action='unassign'), 400)
        record('locked_source_blocks_unassign', p.state==before, response=blocked)
        post('v2/lock', dict(layer_id=1, locked=False))
        post('workflow/masks/bulk', dict(bulk, action='unassign'))
        post('v2/undo', {})
        undo_ok = all(p.candidate(gui_iid,n)['layer_id']==1 for n in original_ids)
        post('v2/redo', {})
        record('unassign_undo_redo_preserves_masks', undo_ok and all(p.candidate(gui_iid,n)['layer_id'] is None and np.array_equal(p.mask(gui_iid,n),original_masks[n]) for n in original_ids))

        proposals = {}
        grid = post('prompts/grid', dict(image_id=source_iid, grid=2))['points']
        for method in ('kmeans','canny','sobel','scharr','hybrid','profile'):
            start=time.perf_counter()
            proposals[method] = post('prompts/ml',dict(image_id=source_iid,method=method,count=2,min_distance=12,existing=grid,denoise='gaussian',sigma=1))
            record('feature_points_'+method, all(len(pt)==2 for pt in proposals[method]['points']),
                   count=len(proposals[method]['points']),warnings=proposals[method]['warnings'],seconds=round(time.perf_counter()-start,3))

        source_candidate=p.candidate(source_iid,1)
        draft=dict(auto_points=grid+proposals['canny']['points'],manual_points=source_candidate['prompts']['points']+[[170,350,0]],
                   box=source_candidate['prompts']['box'],manual_mode='object',feature_settings=proposals['canny']['settings'])
        post('workflow/prompt-presets/save',dict(image_id=source_iid,preset_id='audit_mixed',draft=draft))
        restored=Project(p.root).state['prompt_presets']['audit_mixed']
        record('recipe_grid_canny_manual_box_disk_roundtrip',restored['draft']=={k:draft[k] for k in ('auto_points','manual_points','box','manual_mode')},
               auto_count=len(draft['auto_points']),manual_count=len(draft['manual_points']),feature_settings_preserved=restored['feature_settings']==draft['feature_settings'])
        await job('prepare_recipe_two_images',[source_iid,target_iid],['prompt_transfer'],dict(prompt_transfer=dict(preset_id='audit_mixed',method='normalized')))
        unreviewed_error=None
        try: current_transfer(p,target_iid,reviewed=True)
        except ValueError as exc: unreviewed_error=str(exc)
        record('recipe_requires_per_image_review',bool(unreviewed_error),error=unreviewed_error)
        post('workflow/prompt-transfers/confirm',dict(entries=[dict(image_id=iid,signature=transfer_signature(current_transfer(p,iid))) for iid in (source_iid,target_iid)]))

        start=time.perf_counter()
        post('model/load',dict(checkpoint=args.checkpoint,variant='vit_b',device='cpu'))
        record('actual_sam_loaded',api.model.info is not None,seconds=round(time.perf_counter()-start,3))
        settings=dict(sam=dict(prompt_source='transferred',grid=2,pred_iou=.5,stability=.7,nms=.8))
        await job('real_sam_mixed_recipe_two_images',[source_iid,target_iid],['sam'],settings)
        for iid in (source_iid,target_iid):
            created=[c for c in p.state['candidates'][iid] if c['source'].startswith('transferred-')]
            record('mixed_sources_'+iid, bool(created) and {'transferred-auto','transferred-manual'} <= {c['source'] for c in created}
                   and all(c['layer_id'] is None for c in created), counts={name:sum(c['source']==name for c in created) for name in ('transferred-auto','transferred-manual')})
        for mode in ('grid','features','grid_features'):
            await job('real_sam_'+mode,[target_iid],['sam'],dict(sam=dict(prompt_source=mode,grid=2,pred_iou=.5,stability=.7,nms=.8,features=dict(method='sobel',count=2,denoise='median'))))

        for choice in (0,2):
            before=copy.deepcopy(p.state)
            start=time.perf_counter()
            payload=dict(image_id=source_iid,roi=[35,35,300,260],points=source_candidate['prompts']['points'],box=source_candidate['prompts']['box'],preview=True,mask_choice=choice)
            try:
                preview=post('sam/prompt',payload)
                unchanged=p.state==before
                image=client.get('/api/roi-previews/'+preview['preview_token']+'.png')
                candidate=post('roi-previews/'+preview['preview_token']+'/accept',{})
                reloaded=Project(p.root).candidate(source_iid,candidate['id'])
                record('independent_roi_choice_'+str(choice),unchanged and image.status_code==200 and candidate['area']>0 and reloaded['prompts']['roi']==payload['roi'],
                       seconds=round(time.perf_counter()-start,3),preview=preview,candidate_id=candidate['id'],saved_prompts=reloaded['prompts'])
            except Exception as exc:
                record('independent_roi_choice_'+str(choice),False,error=str(exc))

        # All new SAM candidates remain unassigned. Reuse only original target masks.
        for iid,cid in ((source_iid,1),(target_iid,2)):
            post('workflow/scopes/save',dict(image_id=iid,scope_id='audit_target',candidate_ids=[cid]))
            post('scale/confirm',dict(image_id=iid))
        await job('batch_rotation_selected_masks',[source_iid,target_iid],['rotation'],dict(rotation=dict(scope_id='audit_target',mode='auto',edge='bottom')))
        gate=post('workflow/measurement',dict(image_id=source_iid,config=dict(scope_id='audit_target')),400)
        record('measurement_requires_rotation_confirmation',True,response=gate)
        post('workflow/confirm-many',dict(image_ids=[source_iid,target_iid],kind='rotation'))
        for axis in ('thickness','cd'):
            await job('batch_'+axis+'_without_gt',[source_iid,target_iid],['measurement'],dict(measurement=dict(scope_id='audit_target',axis=axis,step=10)))
        exported=post('workflow/export',dict(image_ids=[source_iid,target_iid],scope_id='audit_target',include_gt=False,export_all_axes=True))
        (out/'both-axes.zip').write_bytes(exported.content)
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            files=archive.namelist()
        reload=Project(p.root)
        record('both_axes_export_reload',all(f'{iid}/measurements/{axis}.json' in files and axis in reload.state['measurements_by_axis'][iid]
                   for iid in (source_iid,target_iid) for axis in ('thickness','cd')),zip_entries=files,
               summaries={iid:{axis:value['summary'] for axis,value in reload.state['measurements_by_axis'][iid].items()} for iid in (source_iid,target_iid)})

    record('source_files_unchanged',all(hashlib.sha256((source/name).read_bytes()).hexdigest()==digest for name,digest in hashes.items()),files=len(hashes))
    print('RESULTS '+str(out/'results.json'),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--checkpoint',required=True)
    asyncio.run(main(parser.parse_args()))
