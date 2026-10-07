"""Deterministic GUI test fixture, explicitly synthetic (not a SAM/expert GT result)."""
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
        raise SystemExit('Refusing to overwrite an existing audit project')
    p = Project(root)
    yy, xx = np.mgrid[:300, :480]
    # Known horizontal edge y=150; masks start with a 10px adjacent overlap.
    gray = np.where(yy < 150, 65, 180).astype(float)
    gray += np.random.default_rng(20261001).normal(0, 3, gray.shape)
    im = np.repeat(np.clip(gray, 0, 255).astype('uint8')[..., None], 3, axis=2)
    buf = io.BytesIO()
    Image.fromarray(im).save(buf, format='PNG')
    iid = p.add_image(buf.getvalue(), 'SYNTHETIC_boundary_overlap_known_y150.png')
    p.state['layers'] = [dict(id=1, name='Synthetic upper', color='#f4a340', locked=False),
                         dict(id=2, name='Synthetic lower', color='#368cdd', locked=False)]
    for lid, mask in ((1, (xx >= 30) & (xx < 450) & (yy >= 30) & (yy < 155)),
                      (2, (xx >= 30) & (xx < 450) & (yy >= 145) & (yy < 270))):
        c = p.put_candidate(iid, mask, 'synthetic-test-fixture-not-sam')
        c.update(layer_id=lid, name=f'Synthetic mask L{lid}', reviewed=False)
    p.save()
    metadata = dict(image_id=iid, true_boundary_y=150, initial_overlap_pixels=4200,
                    synthetic=True, expert_gt=False, purpose='GUI boundary controls, conservation and overlap checks')
    (root.parent / 'fixture.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps(metadata))


if __name__ == '__main__':
    main()
