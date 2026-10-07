"""New isolated GUI fixture; never overwrite an existing project."""
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tem_analyzer.storage import Project


def main():
    root = Path(sys.argv[1]).resolve()
    if (root / 'project.json').exists():
        raise SystemExit('Refusing to overwrite existing project')
    p = Project(root)
    yy, xx = np.mgrid[:300, :480]
    gray = np.where(yy < 150, 65, 180).astype(float)
    gray += np.random.default_rng(20261001).normal(0, 3, gray.shape)
    rgb = np.repeat(np.clip(gray, 0, 255).astype('uint8')[..., None], 3, axis=2)
    out = io.BytesIO(); Image.fromarray(rgb).save(out, format='PNG')
    iid = p.add_image(out.getvalue(), 'SYNTHETIC_gap40_known_edge_y150.png')
    p.state['layers'] = [dict(id=1, name='Upper test layer', color='#f4a340', locked=False),
                         dict(id=2, name='Lower test layer', color='#368cdd', locked=False)]
    for lid, mask in ((1, (xx >= 30) & (xx < 450) & (yy >= 30) & (yy < 130)),
                      (2, (xx >= 30) & (xx < 450) & (yy >= 170) & (yy < 270))):
        c = p.put_candidate(iid, mask, 'synthetic-fixture-not-sam')
        c.update(layer_id=lid, name=f'Synthetic mask L{lid}', reviewed=False)
    p.save()
    report = dict(image_id=iid, synthetic=True, expert_gt=False,
                  known_edge_y=150, gap_width=40, expected_fill_pixels=16800)
    (root.parent/'gui-fixture.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__': main()
