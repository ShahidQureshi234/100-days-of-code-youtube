"""Mode A (B&W Xerox) and Mode B (Smart Color) pipeline tests.

Covers FR-005..FR-008 and success criteria SC-001..SC-003.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from engine.bw_mode import BwSettings, process_bw
from engine.color_mode import ColorSettings, process_color
from engine.detection import detect_document_corners, four_point_transform
from engine.imaging import encode_tiff_g4

from tests.conftest import LOGO_RECT, make_document_page


def _warp_photo(photo_path: Path) -> np.ndarray:
    photo = cv2.cvtColor(cv2.imread(str(photo_path)), cv2.COLOR_BGR2RGB)
    detection = detect_document_corners(photo)
    return four_point_transform(photo, detection.corners)


# --------------------------------------------------------------------------- #
# Mode A -- True B&W (Xerox)
# --------------------------------------------------------------------------- #
def test_bw_output_is_pure_black_and_white(skewed_photo):
    warped = _warp_photo(skewed_photo)
    result = process_bw(warped)

    unique = np.unique(result.binary)
    assert set(unique.tolist()).issubset({0, 255}), f"grey levels leaked: {unique[:10]}"
    # There must be both ink and paper.
    assert result.ink_ratio > 0.005, "no text detected in B&W output"
    assert result.ink_ratio < 0.5, "page flooded with ink (threshold broken)"


def test_bw_removes_shadow_gradient(skewed_photo):
    """SC-003: the illumination gradient must not survive binarization."""
    warped = _warp_photo(skewed_photo)
    result = process_bw(warped)

    h, w = result.binary.shape
    # Sample paper margins (top strip under the headline, left/right rails).
    samples = np.concatenate(
        [
            result.binary[int(h * 0.02) : int(h * 0.04), int(w * 0.05) : int(w * 0.95)].ravel(),
            result.binary[int(h * 0.5) : int(h * 0.52), int(w * 0.01) : int(w * 0.05)].ravel(),
            result.binary[int(h * 0.5) : int(h * 0.52), int(w * 0.95) : int(w * 0.99)].ravel(),
        ]
    )
    white_ratio = float((samples == 255).mean())
    assert white_ratio > 0.999, f"shadow survived in margins: only {white_ratio:.3%} pure white"


def test_bw_encodes_small_tiff_g4(skewed_photo):
    """SC-001: a 300 DPI text page must G4-encode into the KB budget."""
    warped = _warp_photo(skewed_photo)
    result = process_bw(warped)  # defaults: target long edge 3300 (~300 DPI A4)
    tiff = encode_tiff_g4(result.binary, dpi=300)

    assert tiff[:4] == b"II*\x00" or tiff[:4] == b"MM\x00*"
    assert len(tiff) < 150_000, f"CCITT G4 budget blown: {len(tiff)} bytes"
    # And dramatically smaller than a lossless PNG of the same page would be.
    png = cv2.imencode(".png", result.binary)[1].tobytes()
    assert len(tiff) < 0.5 * len(png)


def test_bw_settings_are_respected(skewed_photo):
    warped = _warp_photo(skewed_photo)
    harsh = BwSettings(c=25, block_size=31, unsharp_alpha=0.9)
    result = process_bw(warped, harsh)
    assert set(np.unique(result.binary).tolist()).issubset({0, 255})
    assert 0.0 < result.ink_ratio < 0.5


# --------------------------------------------------------------------------- #
# Mode B -- Smart Color (MRC)
# --------------------------------------------------------------------------- #
def test_color_whitens_background_preserves_logo():
    """SC-002 prerequisites: yellowed paper -> white; logo keeps its hue."""
    page = make_document_page()  # paper tint (250,246,230) -> LAB L ~ 245
    result = process_color(page)

    h, w = result.color_rgb.shape[:2]
    # Margin strip (paper, no content): must be pushed to pure white.
    margin = result.color_rgb[int(h * 0.02) : int(h * 0.045), int(w * 0.06) : int(w * 0.9)]
    assert margin.min() >= 250, f"background not whitened: min={margin.min()}"

    # Logo block keeps a strong red hue (RGB order here).
    lx, ly, lw, lh = LOGO_RECT
    scale_x = w / page.shape[1]
    scale_y = h / page.shape[0]
    cx = int((lx + lw / 2) * scale_x)
    cy = int((ly + lh / 2) * scale_y)
    patch = result.color_rgb[cy - 5 : cy + 5, cx - 5 : cx + 5].reshape(-1, 3)
    r, g, b = patch.mean(axis=0)
    assert r > g + 30 and r > b + 30, f"logo hue lost: rgb=({r:.0f},{g:.0f},{b:.0f})"


def test_color_text_mask_has_ink():
    page = make_document_page()
    result = process_color(page)

    assert set(np.unique(result.text_mask).tolist()).issubset({0, 255})
    assert result.ink_ratio > 0.005, "text mask is empty"
    # Mask ink must sit on dark (text) pixels only.
    gray = cv2.cvtColor(page, cv2.COLOR_RGB2GRAY)
    ink_pixels = result.text_mask == 255
    assert gray[ink_pixels].mean() < 80, "mask ink covers non-text areas"


def test_color_size_budget():
    """SC-002: color page + mask must land under the 350 KB budget."""
    page = make_document_page()
    result = process_color(page)

    ok, jpg = cv2.imencode(
        ".jpg",
        cv2.cvtColor(result.color_rgb, cv2.COLOR_RGB2BGR),
        [int(cv2.IMWRITE_JPEG_QUALITY), 72],
    )
    assert ok
    from engine.color_mode import encode_text_mask_png

    import io

    buf = io.BytesIO()
    encode_text_mask_png(result.text_mask).save(buf, format="PNG", optimize=True)
    total = len(jpg) + len(buf.getvalue())
    assert total < 350_000, f"color page budget blown: {total} bytes"


def test_color_settings_custom():
    page = make_document_page()
    tuned = ColorSettings(white_threshold=200, clahe_clip=3.0, jpeg_quality=75)
    result = process_color(page, tuned)
    h, w = result.color_rgb.shape[:2]
    margin = result.color_rgb[int(h * 0.02) : int(h * 0.045), int(w * 0.06) : int(w * 0.9)]
    assert margin.min() >= 250
