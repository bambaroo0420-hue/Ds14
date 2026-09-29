# Integrated source notices

This version builds on these projects in bambaroo0420-hue/Ds14:

- TEM_Analyzer_v1: application, prompt preparation, calibration and UI.
- TEM_SAM_Boundary_Demo_v2: geometry/normal-gradient DP implementation, adapted in tem_analyzer/geometry.py and boundary.py; API-level paired candidate updates and protected-pixel handling are new in v2.
- TEM_SAM_Lab_v1_2: native residual refiner/model bundle contract and bundled official SAM sources under adaptation_backend.

Original SAM is Apache-2.0. The vendored package and license are retained in adaptation_backend/vendor/segment-anything. Lab's notices, ABL source and license are retained under adaptation_backend. See adaptation_backend/THIRD_PARTY_NOTICES.md for provenance. No pretrained weights are included.
