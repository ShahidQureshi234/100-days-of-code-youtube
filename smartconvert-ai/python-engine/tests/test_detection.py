"""Detection & de-skew tests (FR-002/003/004, SC-004)."""

from __future__ import annotations

import numpy as np
import pytest

from engine.detection import (
    DetectionResult,
    detect_document_corners,
    four_point_transform,
    order_points,
)

from tests.conftest import PAGE_H, PAGE_W, PHOTO_H, PHOTO_W, TRUE_QUAD, make_document_page

TOLERANCE = 0.06  # 6% of frame dimension


def test_order_points_canonical_order():
    shuffled = np.array(
        [
            [80.0, 900.0],   # BL
            [700.0, 60.0],   # TR
            [40.0, 30.0],    # TL
            [720.0, 880.0],  # BR
        ],
        dtype=np.float32,
    )
    ordered = order_points(shuffled)
    assert tuple(ordered[0]) == (40.0, 30.0)    # TL
    assert tuple(ordered[1]) == (700.0, 60.0)   # TR
    assert tuple(ordered[2]) == (720.0, 880.0)  # BR
    assert tuple(ordered[3]) == (80.0, 900.0)   # BL


def test_detects_skewed_document(skewed_photo):
    import cv2  # local import keeps module import graph clean

    photo = cv2.imread(str(skewed_photo))
    photo = cv2.cvtColor(photo, cv2.COLOR_BGR2RGB)
    result = detect_document_corners(photo)

    assert isinstance(result, DetectionResult)
    assert result.method in ("contour", "min-area-rect"), f"detection failed: {result.method}"
    assert result.is_auto

    true = np.array(TRUE_QUAD, dtype=np.float32)
    tol_x = TOLERANCE * PHOTO_W
    tol_y = TOLERANCE * PHOTO_H
    for detected, expected in zip(result.corners, true):
        assert abs(detected[0] - expected[0]) <= tol_x, (detected, expected)
        assert abs(detected[1] - expected[1]) <= tol_y, (detected, expected)


def test_warp_restores_page_geometry(skewed_photo):
    """After de-skew the page must recover roughly its flat aspect ratio."""
    import cv2

    photo = cv2.cvtColor(cv2.imread(str(skewed_photo)), cv2.COLOR_BGR2RGB)
    result = detect_document_corners(photo)
    warped = four_point_transform(photo, result.corners)

    h, w = warped.shape[:2]
    expected_ratio = PAGE_W / PAGE_H
    assert abs((w / h) - expected_ratio) < 0.06, f"aspect drift: {w}/{h} vs {expected_ratio:.3f}"


def test_fallback_when_no_document():
    """Pure noise -> the 5% inner-padded fallback quad (FR-004)."""
    rng = np.random.default_rng(3)
    noise = rng.integers(0, 255, (800, 600, 3), dtype=np.uint8)
    result = detect_document_corners(noise)

    assert result.method == "fallback"
    assert result.confidence == 0.0
    corners = result.corners
    assert corners[0][0] == pytest.approx(0.05 * 600, abs=2)
    assert corners[0][1] == pytest.approx(0.05 * 800, abs=2)
    assert corners[2][0] == pytest.approx(0.95 * 600, abs=2)
    assert corners[2][1] == pytest.approx(0.95 * 800, abs=2)


def test_warp_fills_outside_area_white():
    page = make_document_page()
    corners = np.float32([[0, 0], [PAGE_W - 1, 0], [PAGE_W - 1, PAGE_H - 1], [0, PAGE_H - 1]])
    warped = four_point_transform(page, corners)
    h, w = warped.shape[:2]
    # dst grid is (max-1) sized -- allow a couple of pixels of rounding.
    assert abs(h - PAGE_H) <= 2 and abs(w - PAGE_W) <= 2
