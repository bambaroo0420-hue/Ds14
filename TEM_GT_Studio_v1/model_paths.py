"""All relative model paths are relative to the application, not the shell cwd."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DEFAULTS={
    'segment_anything':{'vit_b':'models/sam/sam_vit_b_01ec64.pth','vit_l':'models/sam/sam_vit_l_0b3195.pth','vit_h':'models/sam/sam_vit_h_4b8939.pth'},
    'micro_sam':{'vit_b':'models/micro_sam/vit_b_em_organelles.pth'},
}
def local_path(value):
    p=Path(value).expanduser()
    return p if p.is_absolute() else ROOT/p

def checkpoint_path(value,backend,model_type):
    value=(value or '').strip() or DEFAULTS.get(backend,{}).get(model_type)
    if not value: raise ValueError('이 조합은 체크포인트 경로를 직접 지정하세요.')
    p=local_path(value)
    if not p.is_file(): raise ValueError(f'가중치가 없습니다: {p}\nWEIGHTS_KO.md의 링크에서 받아 해당 폴더에 넣으세요.')
    return p

def inventory():
    files=[]
    for folder in ('sam','micro_sam'):
        base=ROOT/'models'/folder
        if base.is_dir():
            files.extend(str(p.relative_to(ROOT)).replace('\\','/') for p in base.iterdir() if p.is_file() and p.suffix.lower() in ('.pth','.pt'))
    return sorted(files)
