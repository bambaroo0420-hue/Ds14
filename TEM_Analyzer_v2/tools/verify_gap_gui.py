"""Read-only checks of the isolated project after actual browser operations."""
import json
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.storage import Project
from tem_analyzer.services.layers import unions,active

root=Path(__file__).resolve().parents[1]/'test-output/gap-bridge-20261001'
p=Project(root/'gui-project')
iid=json.loads((root/'gui-fixture.json').read_text())['image_id']
m=unions(p,iid);original=p.mask(iid,1)|p.mask(iid,2)
result=dict(filled_pixels=int(((m[1]|m[2])&~original).sum()),overlap_pixels=int((m[1]&m[2]).sum()),
            remaining_gap_pixels=int((~(m[1]|m[2]))[130:170,30:450].sum()),
            active_candidates=[{'id':c['id'],'layer_id':c['layer_id'],'reviewed':c['reviewed']} for c in active(p,iid)],
            known_edge_max_error_px=int(np.max(abs((299-m[1][::-1].argmax(axis=0))[30:450]-149))),
            synthetic=True,expert_gt=False)
assert result['filled_pixels']==16800 and result['overlap_pixels']==0 and result['remaining_gap_pixels']==0
assert result['known_edge_max_error_px']<=1 and not any(c['reviewed'] for c in active(p,iid))
(root/'gui-result.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result))
