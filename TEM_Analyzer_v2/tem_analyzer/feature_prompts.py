"""Deterministic, model-free prompt proposals. All returned points use original pixels."""
import base64
import io
from typing import Literal
import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field, model_validator
from scipy import ndimage as ndi
from .preprocessing import filtered
from .prompts import ml_points, validate_points


class FeatureConfig(BaseModel):
    method: Literal['kmeans', 'canny', 'sobel', 'scharr', 'hybrid'] = 'kmeans'
    count: int = Field(default=12, ge=1, le=100)
    clusters: int = Field(default=5, ge=2, le=12)
    min_distance: float = Field(default=12, ge=1, le=1000)
    denoise: Literal['none', 'gaussian', 'median', 'bilateral', 'nlm'] = 'none'
    sigma: float = Field(default=1, ge=0, le=4)
    median_size: Literal[3, 5, 7, 9] = 3
    range_sigma: float = Field(default=.08, ge=.01, le=1)
    nlm_h: float = Field(default=10, ge=1, le=40)
    canny_low: float = Field(default=40, ge=0, le=255)
    canny_high: float = Field(default=100, ge=0, le=255)
    gradient_percentile: float = Field(default=75, ge=1, le=99)
    edge_clearance: float = Field(default=3, ge=0, le=50)

    @model_validator(mode='after')
    def thresholds(self):
        if self.canny_low >= self.canny_high:
            raise ValueError('Canny 낮은 임계값은 높은 임계값보다 작아야 합니다.')
        return self


def _cv():
    try:
        import cv2
        return cv2
    except ImportError as exc:
        raise ValueError('OpenCV가 필요합니다. 가상환경에서 pip install -r requirements.txt 를 실행하세요.') from exc


def _edges(gray, allowed, cfg):
    cv = _cv()
    if cfg.method in ('canny', 'hybrid'):
        edge = cv.Canny(gray, cfg.canny_low, cfg.canny_high, L2gradient=True) > 0
    else:
        derivative = cv.Scharr if cfg.method == 'scharr' else cv.Sobel
        gx = derivative(gray, cv.CV_32F, 1, 0)
        gy = derivative(gray, cv.CV_32F, 0, 1)
        magnitude = np.hypot(gx, gy)
        values = magnitude[allowed & (magnitude > 1e-6)]
        edge = magnitude >= np.percentile(values, cfg.gradient_percentile) if values.size else np.zeros_like(allowed)
    return edge & allowed


def propose(image, excluded, existing=(), config=None, preview=False):
    cfg = config if isinstance(config, FeatureConfig) else FeatureConfig(**(config or {}))
    h, w = image.shape[:2]
    validate_points(existing, w, h)
    if excluded.shape != (h, w):
        raise ValueError('제외 영역 크기 불일치')
    # Bounded working resolution: denoise controls are in this analysis pixel space.
    ratio = min(1., 512 / max(h, w))
    ww, hh = max(1, round(w * ratio)), max(1, round(h * ratio))
    small = np.asarray(Image.fromarray(image).resize((ww, hh), Image.Resampling.BILINEAR))
    ex = np.asarray(Image.fromarray(excluded.astype('uint8') * 255).resize((ww, hh), Image.Resampling.BOX)) > 0
    allowed = ~ex
    source = filtered(small, dict(enabled=cfg.denoise != 'none', method=cfg.denoise if cfg.denoise != 'none' else 'gaussian',
        sigma=cfg.sigma, median_size=cfg.median_size, range_sigma=cfg.range_sigma, nlm_h=cfg.nlm_h))
    edges = np.zeros((hh, ww), bool)
    proposals = []
    warnings = []
    if not allowed.any():
        warnings.append('분석할 유효 영역이 없습니다.')
    else:
        clearance = None
        if cfg.method != 'kmeans':
            gray = np.asarray(Image.fromarray(source).convert('L'))
            edges = _edges(gray, allowed, cfg)
            if not edges.any():
                warnings.append('경계를 검출하지 못했습니다. 임계값/노이즈 제거를 조절하세요.')
            else:
                clearance = ndi.distance_transform_edt(np.pad(allowed & ~edges, 1))[1:-1, 1:-1]
                # Connected local maxima, not edge pixels, seed separate SAM candidates.
                safe = (clearance > max(1., cfg.edge_clearance * ratio)) & allowed
                peaks = safe & (clearance == ndi.maximum_filter(clearance, size=5))
                labels, _ = ndi.label(peaks)
                for label, region in enumerate(ndi.find_objects(labels), 1):
                    if region is None:
                        continue
                    coords = np.argwhere(labels[region] == label)
                    center = coords.mean(0)
                    y, x = coords[np.argmin(((coords - center)**2).sum(1))]
                    y, x = y + region[0].start, x + region[1].start
                    proposals.append((float(clearance[y, x]), (x + .5)*w/ww, (y + .5)*h/hh))
        if cfg.method in ('kmeans', 'hybrid'):
            # K-means retains its original implementation and fixed RNG seed.
            dots = ml_points(source, ex, [], cfg.count*3, cfg.clusters, cfg.min_distance*ratio)
            for x, y in dots:
                if cfg.method == 'hybrid' and (clearance is None or clearance[min(hh-1,int(y)),min(ww-1,int(x))] <= max(1.,cfg.edge_clearance*ratio)):
                    continue
                proposals.append((float(max(hh, ww)), x*w/ww, y*h/hh))
    chosen, others = [], [p[:2] for p in existing]
    for _, x, y in sorted(proposals, reverse=True):
        if excluded[min(h-1,int(y)), min(w-1,int(x))]:
            continue
        if any(np.hypot(x-p[0], y-p[1]) < cfg.min_distance for p in others):
            continue
        chosen.append([float(x), float(y)])
        others.append([x, y])
        if len(chosen) >= cfg.count:
            break
    if not chosen:
        warnings.append('추가점이 없습니다. 기존 점 간격·제외 영역·설정을 확인하세요.')
    result = dict(points=chosen, count=len(chosen), method=cfg.method, settings=cfg.model_dump(),
                  inference_run=False, analysis_shape=[hh, ww], warnings=warnings)
    if preview:
        def uri(a):
            b = io.BytesIO();Image.fromarray(a).save(b, format='PNG')
            return 'data:image/png;base64,' + base64.b64encode(b.getvalue()).decode('ascii')
        overlay = source.copy()
        overlay[edges] = [255, 100, 30]
        overlay[ex] = [70, 25, 25]
        canvas = Image.fromarray(overlay);draw = ImageDraw.Draw(canvas)
        for x, y in chosen:
            px, py = x*ww/w, y*hh/h
            draw.ellipse((px-3, py-3, px+3, py+3), fill='#bf87ff', outline='white')
        result.update(filtered_preview=uri(source), proposal_preview=uri(np.asarray(canvas)))
    return result
