from pathlib import Path
import shutil
from .data import dump_json
from .models import safe_load


def export_bundle(checkpoint,destination,inference_cfg=None):
    """Base SAM is intentionally external. Bundle has adaptation weights + API + config."""
    checkpoint=Path(checkpoint);dest=Path(destination)
    if dest.exists():raise FileExistsError(dest)
    dest.mkdir(parents=True)
    root=Path(__file__).resolve().parents[1];pack=safe_load(checkpoint)
    if inference_cfg is not None:
        for key in ('model_type','preprocessing','refiner_width','refine_side'):
            if inference_cfg[key]!=pack['config'][key]:raise ValueError(f'Architecture/preprocessing mismatch: {key}')
        for key in ('mask_threshold','grid_points_per_side','min_pred_area','min_stability','stability_delta','nms_iou'):
            pack['config'][key]=inference_cfg[key]
    import torch
    torch.save(pack,dest/'adaptation.pt')
    dump_json(dest/'inference_settings.json',{k:pack['config'][k] for k in (
        'preprocessing','mask_threshold','grid_points_per_side','min_pred_area','min_stability','stability_delta','nms_iou','refine_side')})
    shutil.copytree(root/'temlab',dest/'temlab',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(root/'vendor',dest/'vendor',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(root/'requirements.txt',dest/'requirements.txt')
    shutil.copy2(root/'THIRD_PARTY_NOTICES.md',dest/'THIRD_PARTY_NOTICES.md')
    dump_json(dest/'model_manifest.json',dict(schema=1,method=pack['method'],base_sam_sha256=pack['base_sha256'],
        model_type=pack['config']['model_type'],preprocessing=pack['config']['preprocessing'],
        output='class-agnostic prompted binary mask',architecture='SAM mask decoder' if pack['method']=='decoder' else 'ResidualRefiner v1',
        note='Use temlab.models.Predictor; loading the file into the unmodified SAM loader is not sufficient.'))
    (dest/'web_adapter_example.py').write_text('''from temlab.models import Predictor
from temlab.data import load_image

# Initialize once in a GPU worker. Do not share mutable set_image state across concurrent users.
predictor = Predictor("/path/to/sam_vit_h_4b8939.pth", "adaptation.pt", device="cuda")
image = load_image("/path/to/new_tem.png", predictor.engine.cfg["preprocessing"])
predictor.set_image(image)
result = predictor.predict(points=[[120, 180]], labels=[1])
mask = result["mask"]
# UI coordinates must be converted from displayed pixels to original-image pixels.
''',encoding='utf-8')
    return str(dest)
