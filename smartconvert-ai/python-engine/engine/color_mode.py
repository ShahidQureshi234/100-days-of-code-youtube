"""Mode B -- Smart Color Preservation engine (MRC-style).

Target: high-detail photos/logos preserved, background yellowing removed,
sharp text, 150-350 KB/page.

Chain (spec-mandated):

  1. Convert to LAB color space and isolate the L (lightness) channel.
  2. CLAHE (contrast limited adaptive histogram equalization) on L --
     lifts detail in shadows without blowing out highlights.
  3. Push light greys / yellowed paper (L > 220) to pure white with a soft
     ramp (no hard halos at shadow boundaries).
  4. Mild unsharp pass keeps text crisp after recompression.
  5. Extract a 1-bit *text mask* (adaptive threshold) for the MRC PDF
     layout: the mask is overlaid on the color layer at export time, so
     glyph strokes never touch the JPEG DCT artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import cv2
import numpy as np
from PIL import Image

#: Defaults mandated by the product specification.
DEFAULT_WHITE_THRESHOLD = 220  # L values above this -> pure white
DEFAULT_WHITE_RAMP = 24        # soft ramp width below the threshold
DEFAULT_CLAHE_CLIP = 2.0       # CLAHE clip limit
DEFAULT_CLAHE_TILES = (8, 8)   # CLAHE tile grid
DEFAULT_JPEG_QUALITY = 72      # color layer quality (70-75 mandated)
DEFAULT_TARGET_LONG_EDGE = 2600
DEFAULT_TEXT_MASK_BLOCK = 15   # adaptive threshold block for the text mask
DEFAULT_TEXT_MASK_C = 10
DEFAULT_TEXT_INK_L_MAX = 150   # only "dark" pixels may become mask ink
DEFAULT_TEXT_INK_MAX_CHROMA = 28.0  # ...and only near-neutral (grey/black) ones
DEFAULT_UNSHARP_ALPHA = 0.35   # mild final sharpening
DEFAULT_ILLUM_KERNEL_PCT = 0.25  # background-estimation window (fraction of long edge)
DEFAULT_ILLUM_DOWNSAMPLE = 8     # speed: estimate the map on a smaller grid


@dataclass(frozen=True)
class ColorSettings:
    white_threshold: int = DEFAULT_WHITE_THRESHOLD
    white_ramp: int = DEFAULT_WHITE_RAMP
    clahe_clip: float = DEFAULT_CLAHE_CLIP
    jpeg_quality: int = DEFAULT_JPEG_QUALITY
    target_long_edge: int = DEFAULT_TARGET_LONG_EDGE
    text_mask_block: int = DEFAULT_TEXT_MASK_BLOCK
    text_mask_c: int = DEFAULT_TEXT_MASK_C
    text_mask_max_chroma: float = DEFAULT_TEXT_INK_MAX_CHROMA
    unsharp_alpha: float = DEFAULT_UNSHARP_ALPHA
    illumination_kernel_pct: float = DEFAULT_ILLUM_KERNEL_PCT
    illumination_downsample: int = DEFAULT_ILLUM_DOWNSAMPLE


@dataclass(frozen=True)
class ColorResult:
    color_rgb: np.ndarray   # cleaned color page (RGB uint8)
    text_mask: np.ndarray   # uint8 {0, 255}; 255 = ink pixel (for MRC overlay)
    ink_ratio: float


def _rescale(image: np.ndarray, target_long_edge: int) -> np.ndarray:
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


def _flatten_illumination(
    l_channel: np.ndarray,
    kernel_pct: float = DEFAULT_ILLUM_KERNEL_PCT,
    downsample: int = DEFAULT_ILLUM_DOWNSAMPLE,
) -> np.ndarray:
    """Divide out the illumination map (shadows/gradients) on L.

    The background is estimated with a **max filter** (dilate) rather than a
    closing: a closing-based map collapses inside large dark regions (logos,
    photos) and washes them out on division, while a max filter always sees
    through to the brightest nearby surface (the paper), so:

      * shadowed paper -> divided up to its true bright level (whitened)
      * logos/photos   -> stay dark relative to paper (preserved)

    The map is computed on a downsampled grid (it is low-frequency by
    nature) and smoothed to avoid banding at shadow boundaries.
    """
    h, w = l_channel.shape[:2]
    ds = max(1, int(downsample))
    sw, sh = max(1, w // ds), max(1, h // ds)
    small = cv2.resize(l_channel, (sw, sh), interpolation=cv2.INTER_AREA)

    kernel_len = int(max(9, round(kernel_pct * max(sh, sw))))
    if kernel_len % 2 == 0:
        kernel_len += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_len, kernel_len))
    bg_small = cv2.dilate(small, kernel)

    background = cv2.resize(bg_small, (w, h), interpolation=cv2.INTER_LINEAR)
    background = cv2.GaussianBlur(background, (31, 31), 0)
    bg = np.maximum(background.astype(np.float32), 1.0)
    flat = l_channel.astype(np.float32) / bg * 255.0
    return np.clip(flat, 0, 255).astype(np.uint8)


def process_color(
    warped_rgb: np.ndarray,
    settings: ColorSettings | None = None,
) -> ColorResult:
    """Run the full Mode B pipeline on a warped (top-down) RGB page."""
    cfg = settings or ColorSettings()

    rgb = _rescale(warped_rgb, cfg.target_long_edge)

    # 1. LAB color space, isolate L.
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    # 1b. Flatten illumination on L (shadow/gradient removal) so paper in
    #     shadowed regions still reaches the whitening threshold below.
    l_flat = _flatten_illumination(l_channel, cfg.illumination_kernel_pct, cfg.illumination_downsample)

    # 2. CLAHE on L (detail/contrast lift for photos and logos).
    clahe = cv2.createCLAHE(
        clipLimit=float(cfg.clahe_clip),
        tileGridSize=(int(DEFAULT_CLAHE_TILES[0]), int(DEFAULT_CLAHE_TILES[1])),
    )
    l_eq = clahe.apply(l_flat)

    # 3. Push light greys / yellowed paper (L > 220) to pure white.
    #    Whiteness must be applied to ALL channels: L -> 255 AND chroma
    #    (a, b) -> neutral 128, otherwise a yellowed page stays yellow.
    if cfg.white_ramp > 0:
        lo = float(max(1, cfg.white_threshold - cfg.white_ramp))
        factor = np.clip((l_eq.astype(np.float32) - lo) / float(cfg.white_ramp), 0.0, 1.0)
    else:
        factor = (l_eq > cfg.white_threshold).astype(np.float32)
    l_white = l_eq.astype(np.float32) * (1.0 - factor) + 255.0 * factor
    a_white = a_channel.astype(np.float32) * (1.0 - factor) + 128.0 * factor
    b_white = b_channel.astype(np.float32) * (1.0 - factor) + 128.0 * factor

    lab_out = cv2.merge(
        [
            np.clip(l_white, 0, 255).astype(np.uint8),
            np.clip(a_white, 0, 255).astype(np.uint8),
            np.clip(b_white, 0, 255).astype(np.uint8),
        ]
    )
    color = cv2.cvtColor(lab_out, cv2.COLOR_LAB2RGB)

    # 4. Mild unsharp mask keeps glyph edges crisp after JPEG recompression.
    if cfg.unsharp_alpha > 0:
        blurred = cv2.GaussianBlur(color, (0, 0), sigmaX=1.5)
        color = np.clip(
            color.astype(np.float32) + cfg.unsharp_alpha * (color.astype(np.float32) - blurred),
            0,
            255,
        ).astype(np.uint8)

    # 5. Text mask for the MRC layout: adaptive threshold on the *original*
    #    (pre-whitening) lightness so ink is judged before we flatten paper.
    block = max(3, int(cfg.text_mask_block) | 1)
    mask = cv2.adaptiveThreshold(
        l_channel,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,  # ink (dark) -> 255
        block,
        float(cfg.text_mask_c),
    )
    # Only genuinely dark AND near-neutral pixels (black/grey text) may be
    # stamped as mask ink.  Saturated colors (logos, colored headings,
    # photos) stay in the color layer underneath -- stamping black over
    # them would destroy the very colors Smart Color mode preserves.
    chroma = np.sqrt(
        (a_channel.astype(np.float32) - 128.0) ** 2 + (b_channel.astype(np.float32) - 128.0) ** 2
    )
    dark_neutral = (l_channel <= DEFAULT_TEXT_INK_L_MAX) & (chroma <= float(cfg.text_mask_max_chroma))
    mask = np.where(dark_neutral, mask, 0).astype(np.uint8)

    ink_ratio = float((mask == 255).mean())
    return ColorResult(color_rgb=color, text_mask=mask, ink_ratio=round(ink_ratio, 5))


def encode_text_mask_png(text_mask: np.ndarray) -> Image.Image:
    """Encode the text mask as a 1-bit PIL image (PDF imagemask source).

    Ink pixels (255) become bit value 1; PIL mode '1' packs rows MSB-first
    which matches PDF imagemask row packing exactly.
    """
    binary = (text_mask > 127).astype(np.uint8) * 255
    return Image.fromarray(binary, mode="L").convert("1", dither=Image.Dither.NONE)
