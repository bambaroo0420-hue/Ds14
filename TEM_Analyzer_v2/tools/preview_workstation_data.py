"""Read-only UI preview data: original test PNG bytes and real saved SAM contours.

No inference, image editing, production project writes or scientific GT creation.
Contour simplification is for screen preview only (never metrology input).
"""
import base64
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def main():
    root = Path(__file__).resolve().parents[1] / 'test-output/selected-scope-v220/project'
    project = json.loads((root / 'project.json').read_text(encoding='utf-8'))
    output = []
    for iid in ('36b757a5e849', '6615e5fea014'):
        info = project['images'][iid]
        image = root / 'images' / f'{iid}.png'
        item = dict(id=iid, **info, src='data:image/png;base64,' + base64.b64encode(image.read_bytes()).decode('ascii'), masks=[])
        for candidate in project['candidates'][iid]:
            with Image.open(root / 'masks' / f"{iid}_{candidate['id']}.png") as handle:
                mask = np.asarray(handle.convert('L'))
            contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            paths = []
            for contour in contours:
                if len(contour) < 3:
                    continue
                pts = cv2.approxPolyDP(contour, 0.65, True).reshape(-1, 2)
                paths.append('M' + 'L'.join(f'{int(x)},{int(y)}' for x, y in pts) + 'Z')
            item['masks'].append(dict(id=candidate['id'], name=candidate['name'], area=candidate['area'],
                                     path=''.join(paths), prompts=candidate['prompts'], source=candidate['source']))
        output.append(item)
    print(json.dumps(output, ensure_ascii=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
