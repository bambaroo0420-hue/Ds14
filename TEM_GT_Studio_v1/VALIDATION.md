# Validation — 2026-09-28

## Passed

- 13 automated pytest tests: horizontal/diagonal/closed normal-DP movement, 3-pixel edge band, ignore handling, project roundtrip, superpixel edit/undo, polyline two-class split, API flow and export, OCR and scale matching, empty OCR/manual float-coordinate exclusion, DOM element IDs/local assets, canonical raster center-to-edge consistency.
- `python -m compileall -q .`
- `node --check static/app.js`
- Synthetic OCR recognized `120k`, `50 nm`, `Sample A-01`; 200 px bar matched to 50 nm, resulting in 0.25 nm/px.
- Flask local server started successfully on 127.0.0.1:8765.

## Not validated here

- Interactive browser mouse/keyboard behavior and screenshot layout: Chromium download failed in the execution environment. JavaScript syntax, element references and server routes were checked; this is not a browser interaction test.
- Actual SAM/micro-SAM checkpoint inference: torch/checkpoints unavailable in this environment. Adapter follows published APIs and requires local checkpoint files.
- Actual semiconductor TEM accuracy, Korean OCR, Windows installation/CUDA, offline dependency provisioning.

No semiconductor/company images or model weights are included. Synthetic tests do not establish metrology accuracy. Please begin with the built-in example and one image, save the project ZIP, and report errors or screenshots.
