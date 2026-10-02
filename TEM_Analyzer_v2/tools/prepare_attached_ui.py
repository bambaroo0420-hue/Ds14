"""Prepare a separate GUI review of the actual attached-image audit, no new SAM."""
import argparse
import copy
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.storage import Project
from tem_analyzer.services.scopes import save_scope
from tem_analyzer.services.layers import fingerprint

p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
out=Path(a.output)
if out.exists():raise ValueError('Use a new destination.')
shutil.copytree(a.source,out);project=Project(out)
for iid in project.state['images']:
    items=[c for c in project.state['candidates'][iid] if c.get('active',True) and not c.get('deleted')]
    for c in project.state['candidates'][iid]:c.update(layer_id=None,reviewed=False)
    save_scope(project,iid,'target',[c['id'] for c in items])
    proposal=project.state['annotation_proposals'][iid];proposal['input_hash']=fingerprint(project,iid)
    project.state['scale'][iid]=copy.deepcopy(proposal['scale'])
project.save();print(project.root)
