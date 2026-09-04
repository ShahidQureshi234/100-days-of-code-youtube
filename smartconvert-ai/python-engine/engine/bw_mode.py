"""Mode A -- True Black & White "Xerox" engine.

Target: ultra-small output (20-80 KB/page), 100% sharp text, 0% grey
background shadow.  The chain (spec-mandated):

  1. Illumination map via morphological closing (21x21 kernel): estimates
     the paper's lighting gradient (shadows, vignetting) while ignoring
     dark text strokes, then divides it out -> flat white paper.
  2. Unsharp masking (alpha = 0.5): locks text stroke edges so thin serif
     details survive binarization.
  3. Adaptive thresholding (Gaussian C, blockSize = 15, C = 10): local
     decision per pixel -> pure black ink on pure white paper.
  4. Despeckle: connected components smaller than a dot of ink are removed.
  5. CCITT Group 4 TIFF encoding (see :func:`engine.imaging.encode_tiff_g4`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import cv2
import numpy as np

#: Defaults mandated by the product specification.
DEFAULT_CLOSE_SIZE = 21        # illumination-map closing kernel (odd)
DEFAULT_UNSHARP_ALPHA = 0.5    # unsharp mask strength
DEFAULT_BLOCK_SIZE = 15        # adaptive threshold neighborhood (odd, >= 3)
DEFAULT_C = 10                 # adaptive threshold constant subtracted from mean
DEFAULT_TARGET_LONG_EDGE = 3300  # ~A4 long edge at 300 DPI
DEFAULT_DESPECKLE_MAX_AREA = 4  # px^2 -- keeps dots on i/j, kills dust


@dataclass(frozen=True)
class BwSettings:
    """Tunable knobs for the B&W pipeline (all spec defaults included)."""

    close_size: int = DEFAULT_CLOSE_SIZE
    unsharp_alpha: float = DEFAULT_UNSHARP_ALPHA
    block_size: int = DEFAULT_BLOCK_SIZE
    c: int = DEFAULT_C
    target_long_edge: int = DEFAULT_TARGET_LONG_EDGE
    despeckle: bool = True
    despeckle_max_area: int = DEFAULT_DESPECKLE_MAX_AREA


@dataclass(frozen=True)
class BwResult:
    binary: np.ndarray  # uint8, values {0, 255}
    ink_ratio: float    # fraction of black pixels (diagnostic)


def _rescale_to_target(image: np.ndarray, target_long_edge: int) -> np.ndarray:
    """Normalize resolution: cap the long edge (300 DPI A4 = 3300 px)."""
    h, w = image.shape[:2]
    long_edge = max(h, w)
    if target_long_edge <= 0 or long_edge <= target_long_edge:
        return image
    scale = float(target_long_edge) / float(long_edge)
    return cv2.resize(
        image,
        (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
        interpolation=cv2.INTER_AREA,
    )


def _illumination_correct(gray: np.ndarray, close_size: int) -> np.ndarray:
    """Divide out the illumination map (shadows / gradients -> flat white)."""
    if close_size < 3:
        close_size = 3
    if close_size % 2 == 0:
        close_size += 1  # cv2 kernels must be odd

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (close_size, close_size))
    # Closing removes dark strokes smaller than the kernel, leaving the
    # paper background (with its lighting gradient) behind.
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    # A little blur keeps the map smooth so division cannot amplify noise.
    background = cv2.GaussianBlur(background, (close_size, close_size), 0)

    bg = background.astype(np.float32)
    bg = np.maximum(bg, 1.0)  # guard against division by zero
    normalized = gray.astype(np.float32) / bg * 255.0
    return np.clip(normalized, 0.0, 255.0).astype(np.float32)


def _unsharp_mask(image_f32: np.ndarray, alpha: float, sigma: float = 2.0) -> np.ndarray:
    """Unsharp masking: image + alpha * (image - gaussian(image))."""
    blurred = cv2.GaussianBlur(image_f32, (0, 0), sigmaX=sigma)
    sharpened = image_f32 + float(alpha) * (image_f32 - blurred)
    return np.clip(sharpened, 0.0, 255.0)


def _adaptive_threshold(image_f32: np.ndarray, block_size: int, c: int) -> np.ndarray:
    """Gaussian-C adaptive threshold on a float image -> {0, 255} uint8."""
    if block_size < 3:
        block_size = 3
    if block_size % 2 == 0:
        block_size += 1
    source = np.clip(image_f32, 0, 255).astype(np.uint8)
    return cv2.adaptiveThreshold(
        source,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        float(c),
    )


def _despeckle(binary: np.ndarray, max_area: int) -> np.ndarray:
    """Remove connected black blobs with area <= *max_area* px^2."""
    if max_area <= 0:
        return binary
    ink = (binary == 0).astype(np.uint8)  # 1 where black
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    if count <= 2:
        return binary
    # Component 0 is background; drop tiny ink components.
    small = np.zeros(count, dtype=bool)
    areas = stats[:, cv2.CC_STAT_AREA]
    small[1:] = areas[1:] <= max_area
    if not small.any():
        return binary
    remove_mask = small[labels]
    ink[remove_mask] = 0
    return (1 - ink) * 255  # back to {0, 255} with 255 = white


def process_bw(
    warped_rgb: np.ndarray,
    settings: BwSettings | None = None,
) -> BwResult:
    """Run the full Mode A pipeline on a warped (top-down) RGB page."""
    cfg = settings or BwSettings()

    # 0. Normalize resolution.
    rgb = _rescale_to_target(warped_rgb, cfg.target_long_edge)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # 1. Illumination map (morphological closing 21x21) -> shadow-free page.
    flat = _illumination_correct(gray, cfg.close_size)

    # 2. Unsharp masking (alpha=0.5) -> locked stroke edges.
    sharp = _unsharp_mask(flat, cfg.unsharp_alpha)

    # 3. Adaptive thresholding (Gaussian C, blockSize=15, C=10).
    binary = _adaptive_threshold(sharp, cfg.block_size, cfg.c)

    # 4. Despeckle (dust / sensor noise), preserving i/j dots.
    if cfg.despeckle:
        binary = _despeckle(binary, cfg.despeckle_max_area)

    ink_ratio = float((binary == 0).mean())
    return BwResult(binary=binary, ink_ratio=round(ink_ratio, 5))
