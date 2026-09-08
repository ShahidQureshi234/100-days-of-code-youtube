"""Shared pytest fixtures: synthetic "photographed document" generator.

The generator produces deterministic, realistic test photos:
  * an A4 page of text-like paragraphs, a table, a headline and a red logo
  * placed on a dark desk with a strong perspective skew
  * shot under an uneven lighting gradient (shadow top-left -> bright
    bottom-right) plus sensor noise and JPEG compression

Because the ground-truth quad is known, detection accuracy, de-skew
geometry, shadow removal and size budgets are all assertable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

PAGE_W, PAGE_H = 1240, 1754  # A4 at 150 DPI
PHOTO_W, PHOTO_H = 1600, 1200
#: Ground-truth document quad inside the photo (TL, TR, BR, BL).
# Perspective-plausible portrait placement: mild skew + foreshortening,
# recovered aspect ratio stays within ~6% of the flat page (0.707).
TRUE_QUAD: List[List[float]] = [
    [560.0, 40.0],
    [1310.0, 45.0],
    [1335.0, 1145.0],
    [535.0, 1140.0],
]
#: Logo placement on the *page* (x, y, w, h) in page pixels.
LOGO_RECT = (900, 90, 220, 140)


def _text_block(
    canvas: np.ndarray,
    rng: np.random.Generator,
    x: int,
    y: int,
    width: int,
    line_height: int,
    n_lines: int,
    color: Tuple[int, int, int] = (20, 20, 20),
) -> None:
    """Draw a paragraph of 'words' (rounded rects) -- text-like statistics."""
    for line in range(n_lines):
        cy = y + line * line_height
        if cy + line_height // 2 >= PAGE_H - 40:
            break
        cx = x
        while cx < x + width - 12:
            word_w = int(rng.integers(18, 60))
            word_h = max(3, line_height // 3)
            cv2.rectangle(
                canvas,
                (cx, cy + line_height // 3),
                (min(cx + word_w, x + width), cy + line_height // 3 + word_h),
                color,
                thickness=-1,
            )
            cx += word_w + int(rng.integers(6, 14))


def make_document_page() -> np.ndarray:
    """Render the flat 'paper' content as an **RGB** array (yellowed paper)."""
    rng = np.random.default_rng(42)
    page = np.zeros((PAGE_H, PAGE_W, 3), dtype=np.uint8)
    page[:] = (250, 246, 228)  # yellowed white paper (RGB; LAB L ~ 245)

    # Headline (bold, large).
    cv2.rectangle(page, (90, 80), (760, 118), (15, 15, 15), thickness=-1)

    # Red logo block (top-right) -- must survive color mode.  RGB red.
    lx, ly, lw, lh = LOGO_RECT
    page[ly : ly + lh, lx : lx + lw] = (205, 45, 45)
    cv2.rectangle(page, (lx, ly), (lx + lw, ly + lh), (20, 20, 20), thickness=4)

    # Two paragraphs.
    _text_block(page, rng, 90, 170, 1060, 34, 12)
    _text_block(page, rng, 90, 620, 1060, 34, 12)

    # Table with ruled lines.
    top, bottom, left, right = 1080, 1450, 90, 1150
    for row in range(5):
        y = top + row * (bottom - top) // 4
        cv2.line(page, (left, y), (right, y), (30, 30, 30), thickness=3)
    cv2.line(page, (left, top), (left, bottom), (30, 30, 30), thickness=3)
    cv2.line(page, (right, top), (right, bottom), (30, 30, 30), thickness=3)
    _text_block(page, rng, left + 20, top + 25, 1000, 40, 8)

    # Signature block + footer rule.
    _text_block(page, rng, 90, 1500, 500, 34, 5)
    cv2.line(page, (90, 1690), (1150, 1690), (40, 40, 40), thickness=3)
    return page


def make_skewed_photo(path: Path, quality: int = 92) -> Path:
    """Render the photographed version (skew + shadow + noise + JPEG)."""
    page = make_document_page()  # RGB
    src_quad = np.float32([[0, 0], [PAGE_W - 1, 0], [PAGE_W - 1, PAGE_H - 1], [0, PAGE_H - 1]])
    dst_quad = np.float32(TRUE_QUAD)
    matrix = cv2.getPerspectiveTransform(src_quad, dst_quad)

    photo = cv2.warpPerspective(
        cv2.cvtColor(page, cv2.COLOR_RGB2BGR),  # cv2.imwrite expects BGR
        matrix,
        (PHOTO_W, PHOTO_H),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(34, 40, 48),  # dark wooden desk (BGR)
    )

    # Uneven illumination: 0.72 top-left -> 1.04 bottom-right.
    yy, xx = np.mgrid[0:PHOTO_H, 0:PHOTO_W].astype(np.float32)
    gain = 0.72 + 0.32 * (xx / PHOTO_W) * 0.55 + 0.32 * (yy / PHOTO_H) * 0.45
    photo = np.clip(photo.astype(np.float32) * gain[..., None], 0, 255).astype(np.uint8)

    # Sensor noise.
    rng = np.random.default_rng(7)
    photo = np.clip(photo + rng.normal(0, 4.0, photo.shape), 0, 255).astype(np.uint8)

    cv2.imwrite(str(path), photo, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return path


@pytest.fixture(scope="session")
def skewed_photo(tmp_path_factory) -> Path:
    """One shared synthetic photo for the whole test session."""
    out = tmp_path_factory.mktemp("fixtures") / "skewed_document.jpg"
    return make_skewed_photo(out)


@pytest.fixture()
def workdir(tmp_path) -> Path:
    """A fresh engine workspace per test."""
    d = tmp_path / "work"
    d.mkdir()
    return d
