# Validation — v1.1, 2026-09-28

## Passed

- 18 pytest tests, including existing normal-DP / GT / project / API regressions.
- EasyOCR adapter contract using a fake Reader: local weight path, CPU, `download_enabled=False`, cache reuse, low-confidence exclusion boxes.
- Required weight files for English vs Korean, missing-weight failure before OCR import, relative SAM path independent of working directory.
- Split number/unit matching and magnification exclusion from scale interpretation.
- `python -m compileall -q .` and `node --check static/app.js`.

## Not validated here

- Real EasyOCR weight inference (English or Korean), and actual SAM/micro-SAM checkpoint inference: weights are deliberately not bundled/downloaded. OCR integration tests inject fixture recognition results. They do NOT measure OCR recognition accuracy.
- Browser mouse/keyboard interaction and screenshot layout. JavaScript syntax, element references and server API were checked.
- Actual semiconductor TEM data, Windows/CUDA installation and offline dependency provisioning.

v1.1 removes Tesseract. The older v1 synthetic Tesseract recognition result is not an EasyOCR validation result.
