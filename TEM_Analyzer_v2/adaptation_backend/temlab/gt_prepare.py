"""Offline notebook helpers for reviewed color GT and rectangular ignore regions."""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def excluded(shape, rectangles):
    h, w = shape[:2]
    out = np.zeros((h, w), bool)
    for rect in rectangles:
        if len(rect) != 4 or any(int(v) != v for v in rect):
            raise ValueError('Rectangle must be four integer coordinates: x0,y0,x1,y1')
        x0, y0, x1, y1 = map(int, rect)
        if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
            raise ValueError(f'Rectangle outside image {w}x{h}: {rect}')
        out[y0:y1, x0:x1] = True
    return out


def preview(image, gt, rectangles):
    if image.shape[:2] != gt.shape[:2]:
        raise ValueError('Image and GT dimensions must match; do not resize GT automatically.')
    excluded(image.shape, rectangles)
    if gt.ndim == 2:
        # Discrete labels: ignore=255 must not compress foreground color contrast.
        color_gt = plt.get_cmap('tab20')((gt.astype(int) % 20) / 19)[..., :3]
        color_gt[gt == 0] = [0, 0, 0]
        color_gt[gt == 255] = [1, 0, 1]
        gt = color_gt
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    for ax, a, title in zip(axes, [image, gt], ['Original: pixel coordinates', 'GT: excluded rectangles']):
        ax.imshow(a, interpolation='nearest')
        ax.set_title(title)
        for x0, y0, x1, y1 in rectangles:
            ax.add_patch(Rectangle((x0-.5, y0-.5), x1-x0, y1-y0,
                                   edgecolor='magenta', facecolor='magenta', alpha=.3))
        ax.set_xlabel('x'); ax.set_ylabel('y')
    plt.tight_layout()
    return fig


def color_candidates(rgb, rectangles, n_colors=8):
    if not 2 <= int(n_colors) <= 64:
        raise ValueError('n_colors must be 2..64; these are candidates, not semantic classes.')
    ignore = excluded(rgb.shape, rectangles)
    pixels = rgb[~ignore]
    if not len(pixels):
        raise ValueError('All pixels excluded.')
    # Deterministic sample; palette discovery ignores text/scale rectangles.
    rng = np.random.default_rng(42)
    sample = pixels[rng.choice(len(pixels), min(len(pixels), 200000), replace=False)]
    q = Image.fromarray(sample.reshape(-1, 1, 3)).quantize(colors=int(n_colors))
    ids = np.unique(np.asarray(q))
    palette = np.asarray(q.getpalette(), dtype=np.uint8).reshape(-1, 3)[ids]
    # Chunked distances avoid an H*W*K*3 allocation for large TEM images.
    flat = rgb.reshape(-1, 3)
    assignment = np.empty(len(flat), np.int32)
    for start in range(0, len(flat), 50000):
        delta = flat[start:start+50000, None].astype(np.float32) - palette[None].astype(np.float32)
        assignment[start:start+50000] = (delta**2).sum(-1).argmin(-1)
    assignment = assignment.reshape(rgb.shape[:2])
    assignment[ignore] = -1
    return assignment, palette


def show_candidates(assignment, palette):
    n = len(palette)
    fig, axes = plt.subplots((n+3)//4, 4, figsize=(16, 3.5*((n+3)//4)), squeeze=False)
    for i, ax in enumerate(axes.flat):
        ax.axis('off')
        if i < n:
            ax.imshow(assignment == i, cmap='gray', interpolation='nearest')
            ax.set_title(f'{i}: RGB {tuple(map(int, palette[i]))}\n{int((assignment == i).sum())} pixels')
    plt.tight_layout()
    return fig


def mapped_labels(assignment, candidate_to_label, class_names):
    present = set(map(int, np.unique(assignment))) - {-1}
    if not present.issubset(candidate_to_label):
        raise ValueError(f'Assign every candidate, missing: {present-set(candidate_to_label)}')
    allowed = {0, 255} | {int(k) for k in class_names}
    if any(not 1 <= int(k) <= 254 for k in class_names):
        raise ValueError('Class IDs must be 1..254; 0 background, 255 ignore.')
    if any(v not in allowed for v in candidate_to_label.values()):
        raise ValueError('Label missing from CLASS_NAMES.')
    labels = np.full(assignment.shape, 255, np.uint8)
    for candidate, label in candidate_to_label.items():
        labels[assignment == candidate] = label
    if not np.any((labels != 0) & (labels != 255)):
        raise ValueError('No foreground remains.')
    return labels


def save_review(labels, output, source_gt, rectangles, palette, mapping, class_names):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Original GT is never replaced. Each reviewed output can be revised.
    if output.resolve() == Path(source_gt).resolve():
        raise ValueError('Output must differ from source GT.')
    Image.fromarray(labels).save(output)
    metadata = dict(source_gt=str(Path(source_gt).resolve()),
                    source_sha256=hashlib.sha256(Path(source_gt).read_bytes()).hexdigest(),
                    output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                    rectangles=rectangles, palette=palette.tolist(),
                    candidate_to_label=mapping, class_names=class_names,
                    ignored_fraction=float((labels == 255).mean()), reviewed=True)
    output.with_suffix('.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
    return metadata
