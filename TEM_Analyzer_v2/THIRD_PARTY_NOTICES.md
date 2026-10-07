# Integrated source notices

This version builds on these projects in bambaroo0420-hue/Ds14:

- TEM_Analyzer_v1: application, prompt preparation, calibration and UI.
- TEM_SAM_Boundary_Demo_v2: geometry/normal-gradient DP implementation, adapted in tem_analyzer/geometry.py and boundary.py; API-level paired candidate updates and protected-pixel handling are new in v2.
- TEM_SAM_Lab_v1_2: native residual refiner/model bundle contract and bundled official SAM sources under adaptation_backend.

Original SAM is Apache-2.0. The vendored package and license are retained in adaptation_backend/vendor/segment-anything. Lab's notices, ABL source and license are retained under adaptation_backend. See adaptation_backend/THIRD_PARTY_NOTICES.md for provenance. No pretrained weights are included.

## v2.1 additions

- The existing normal-gradient cyclic-DP implementation is extended by `services/layers.py` to operate on layer unions and shared interfaces. New layer matching, rigid transforms and contour-intersection measurement code are original additions to this repository; no unidentified GitHub snippets were copied.
- OpenCV Intelligent Scissors was reviewed as a graph-based reference, not substituted for normal-band DP and not vendored: https://github.com/opencv/opencv/blob/4.x/modules/imgproc/src/intelligent_scissors.cpp (OpenCV Apache-2.0).
- SciPy (BSD-3-Clause) supplies distance transforms, connected components and affine resampling: https://github.com/scipy/scipy . NumPy (BSD-3-Clause), Pillow (HPND) and Matplotlib (PSF-compatible license) retain their upstream package licenses.
- EasyOCR 1.7.2 (Apache-2.0): https://github.com/JaidedAI/EasyOCR . Only the installed package and separately supplied official weights are used. OCR model auto-download is disabled. Official SAM: https://github.com/facebookresearch/segment-anything .
