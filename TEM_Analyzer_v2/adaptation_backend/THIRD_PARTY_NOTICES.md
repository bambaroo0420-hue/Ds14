# Third-party source

- Meta / facebookresearch/segment-anything, original SAM (ViT-B/L/H), Apache-2.0.
  Source: https://github.com/facebookresearch/segment-anything
  Retrieved main archive on 2026-09-29. Only Python package and installation/license files are included.
  License: `vendor/segment-anything/LICENSE`. Weights are NOT included.
- Chi Wang et al., Active Boundary Loss for Semantic Segmentation, AAAI 2022, Apache-2.0.
  Source: https://github.com/wangchi95/active-boundary-loss
  Paper: https://ojs.aaai.org/index.php/AAAI/article/view/20139
  Original retrieved code: `vendor/abl_upstream.py`; license: `vendor/ABL_LICENSE`.
  Adapted code: `temlab/abl.py`.

ABL adaptations: remove hardcoded CUDA allocation; support current NumPy;
replace external label-smoothing helper with PyTorch uniform label smoothing;
use equivalent SciPy distance transform for boundary distance; correct boolean
indexing for current PyTorch; return a differentiable zero for empty cases;
exclude unlabelled pixels and their neighboring band from boundary selection.
The directional KL objective, neighbor-detach operation and distance weighting
are retained. This is an adapted implementation, not an exact reproduction of
the authors' training settings or results. The upstream original is preserved
for review. The complete source hash manifest is in the original TEM_SAM_Lab_v1_2 distribution.

No MTP-MAVED code/weights or HQ-SAM weights are included. The experiments in this
package implement original SAM decoder fine-tuning and a separate residual refiner.
