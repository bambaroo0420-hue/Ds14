"""Notebook setup helpers. No GPU allocation or network request at import time."""
from pathlib import Path
import hashlib
import json
import os

SAM_H = {
    'repo_id': 'facebook/ov-seg',
    'repo_type': 'space',
    'revision': '9d3c6962221b4d40fdb61c59befa9b2fddc17621',
    'filename': 'sam_vit_h_4b8939.pth',
    'size': 2564550879,
    'sha256': 'a7bf3b02f3ebf1267aba913ff637d9a2d5c33d3173bb679e46d9f338c26f262e',
}


def verify_checkpoint(path, expected=None):
    expected = SAM_H if expected is None else expected
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size != expected['size']:
        raise ValueError(f'Checkpoint size mismatch: {path}. Partial download, HTML, or Git LFS pointer? '
                         'Preserve/rename this file and rerun download.')
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != expected['sha256']:
        raise ValueError(f'Checkpoint SHA256 mismatch: {path}. Do not use it for training. '
                         'Preserve/rename this file and download again.')
    return path.resolve()


def download_sam_h(weights_dir, *, local_only=False, disable_xet=False):
    """Pinned original-SAM checkpoint, reused offline when already verified.

    Hugging Face Transformers sam-vit-huge weights use another state format and
    are intentionally not downloaded. Token=False avoids sending saved credentials
    for this public file. Standard company proxy/CA environment settings are honored.
    """
    weights_dir = Path(weights_dir).resolve()
    weights_dir.mkdir(parents=True, exist_ok=True)
    path = weights_dir / SAM_H['filename']
    if path.is_file():
        verified = verify_checkpoint(path)
        print('Verified existing SAM ViT-H:', verified)
        return verified
    if local_only:
        raise FileNotFoundError(f'Local-only mode: place {SAM_H["filename"]} in {weights_dir}')
    if disable_xet:
        # HF environment flags are read at import. Notebook uses a fresh process.
        os.environ['HF_HUB_DISABLE_XET'] = '1'
    from huggingface_hub import hf_hub_download
    print('Downloading original SAM ViT-H (2.56 GB) from Hugging Face... ', flush=True)
    downloaded = hf_hub_download(
        repo_id=SAM_H['repo_id'], repo_type=SAM_H['repo_type'],
        revision=SAM_H['revision'], filename=SAM_H['filename'],
        local_dir=str(weights_dir), token=False,
    )
    verified = verify_checkpoint(downloaded)
    (weights_dir / 'sam_download_manifest.json').write_text(
        json.dumps(SAM_H, indent=2), encoding='utf-8')
    print('Size and SHA256 verified:', verified)
    return verified
