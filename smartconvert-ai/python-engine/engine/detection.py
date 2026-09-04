"""Document border detection and perspective de-skew.

Pipeline (mandated by the product spec, mirrors classic scanner firmware):

    Grayscale -> Gaussian Blur (kernel 5x5, sigma 0)
              -> Canny Edge Detection (threshold1=50, threshold2=150)
              -> cv2.findContours
              -> cv2.approxPolyDP (quad extraction)
              -> cv2.getPerspectiveTransform + cv2.warpPerspective

Detection runs on a downscaled copy (fast + noise-tolerant), then the
winning quad is mapped back to full-resolution pixel coordinates.  When no
confident quad exists the module falls back to a 5% inner-padded crop of
the full frame, exactly like a copier that "couldn't find the edges".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import cv2
import numpy as np

#: Downscale target for the detection pass (longest edge, pixels).
DETECT_MAX_EDGE = 1000

#: A credible document must cover at least this fraction of the frame.
MIN_DOCUMENT_AREA_RATIO = 0.15

#: Canny thresholds (spec-mandated).
CANNY_LOW, CANNY_HIGH = 50, 150

#: Inset used by the fallback crop (fraction of each dimension).
FALLBACK_INSET = 0.05

#: Canny edge coverage above this means "texture/noise, no document scene".
MAX_EDGE_DENSITY = 0.25

#: Interior angles of a credible document quad (degrees).
MIN_CORNER_ANGLE, MAX_CORNER_ANGLE = 60.0, 120.0


@dataclass(frozen=True)
class DetectionResult:
    """Ordered quad (TL, TR, BR, BL) in *pixel* coordinates + provenance."""

    corners: np.ndarray  # shape (4, 2), float32
    method: str  # "contour" | "min-area-rect" | "fallback"
    confidence: float  # 0..1 heuristic

    @property
    def is_auto(self) -> bool:
        return self.method != "fallback"


def order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as (top-left, top-right, bottom-right, bottom-left).

    Uses the classic sum/diff trick:
      * top-left has the smallest x+y, bottom-right the largest
      * top-right has the smallest y-x, bottom-left the largest
    """
    pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
    if pts.shape[0] != 4:
        raise ValueError(f"expected 4 points, got {pts.shape[0]}")
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()  # y - x
    return np.array(
        [
            pts[np.argmin(s)],  # top-left
            pts[np.argmin(d)],  # top-right
            pts[np.argmax(s)],  # bottom-right
            pts[np.argmax(d)],  # bottom-left
        ],
        dtype=np.float32,
    )


def _clip_to_frame(corners: np.ndarray, width: int, height: int) -> np.ndarray:
    """Clamp corners to lie just inside the frame (with a tiny margin)."""
    margin = 1.0
    out = corners.copy()
    out[:, 0] = np.clip(out[:, 0], margin, max(margin, width - 1 - margin))
    out[:, 1] = np.clip(out[:, 1], margin, max(margin, height - 1 - margin))
    return out


def _quad_area(corners: np.ndarray) -> float:
    """Shoelace area of the quad (works for convex quads)."""
    x, y = corners[:, 0], corners[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _edge_length_score(corners: np.ndarray) -> float:
    """Ratio shortest-side / longest-side -- near 1.0 means a tidy quad."""
    (tl, tr, br, bl) = corners
    edges = [
        np.linalg.norm(tr - tl),
        np.linalg.norm(br - tr),
        np.linalg.norm(bl - br),
        np.linalg.norm(tl - bl),
    ]
    longest = max(edges) or 1.0
    return min(edges) / longest


def _quad_is_sane(quad: np.ndarray) -> bool:
    """A document quad has four near-right-angle corners (60-120 deg)."""
    for i in range(4):
        corner = quad[i]
        prev_pt = quad[(i - 1) % 4]
        next_pt = quad[(i + 1) % 4]
        v1 = prev_pt - corner
        v2 = next_pt - corner
        norm_product = float(np.linalg.norm(v1) * np.linalg.norm(v2))
        if norm_product < 1e-6:
            return False
        cos_angle = float(np.clip(np.dot(v1, v2) / norm_product, -1.0, 1.0))
        angle = float(np.degrees(np.arccos(cos_angle)))
        if not (MIN_CORNER_ANGLE <= angle <= MAX_CORNER_ANGLE):
            return False
    return True


def _fallback_result(width: int, height: int) -> DetectionResult:
    """The 5%-inset full-frame quad used when detection fails (FR-004)."""
    inset_x = FALLBACK_INSET * width
    inset_y = FALLBACK_INSET * height
    fallback = np.array(
        [
            [inset_x, inset_y],
            [width - 1 - inset_x, inset_y],
            [width - 1 - inset_x, height - 1 - inset_y],
            [inset_x, height - 1 - inset_y],
        ],
        dtype=np.float32,
    )
    return DetectionResult(corners=fallback, method="fallback", confidence=0.0)


def detect_document_corners(image_rgb: np.ndarray) -> DetectionResult:
    """Find the dominant document quad in *image_rgb* (RGB uint8 array).

    Returns a :class:`DetectionResult` whose ``corners`` are full-resolution
    pixel coordinates ordered TL, TR, BR, BL.  Never raises for "no document
    found" -- the fallback result is returned instead.
    """
    height, width = image_rgb.shape[:2]
    frame_area = float(height * width)

    # ---- 1. Downscale for the detection pass (speed + noise tolerance) ----
    scale = min(1.0, DETECT_MAX_EDGE / float(max(height, width)))
    if scale < 1.0:
        small = cv2.resize(image_rgb, (int(round(width * scale)), int(round(height * scale))), interpolation=cv2.INTER_AREA)
    else:
        small = image_rgb
    sh, sw = small.shape[:2]
    small_area = float(sh * sw)

    # ---- 2. Grayscale -> Gaussian blur (5x5, sigma 0) -> Canny (50, 150) ----
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), sigmaX=0, sigmaY=0)
    edges = cv2.Canny(blurred, CANNY_LOW, CANNY_HIGH)

    # A real "document on a desk" photo has sparse edges (paper vs. desk).
    # If edges cover most of the frame the input is texture/noise -- there
    # is no document structure to find, so fall back immediately.
    edge_density = float(np.count_nonzero(edges)) / float(edges.size)
    if edge_density > MAX_EDGE_DENSITY:
        return _fallback_result(width, height)

    # Close tiny gaps in the document border so the outer contour is closed.
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    # ---- 3. Contours -> quad candidates ----
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        ranked = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
        for contour in ranked:
            area = float(cv2.contourArea(contour))
            if area < MIN_DOCUMENT_AREA_RATIO * small_area:
                break  # sorted descending -- nothing bigger remains

            perimeter = cv2.arcLength(contour, closed=True)
            for epsilon_ratio in (0.02, 0.03, 0.05):
                approx = cv2.approxPolyDP(contour, epsilon_ratio * perimeter, True)
                flat = approx.reshape(-1, 2)
                if len(flat) == 4:
                    quad = order_points(flat)
                    if not cv2.isContourConvex(quad.astype(np.float32)):
                        continue
                    if not _quad_is_sane(quad):
                        continue
                    quad_area = _quad_area(quad)
                    if quad_area < MIN_DOCUMENT_AREA_RATIO * small_area:
                        continue
                    # Map back to full-resolution coordinates.
                    full = quad / scale
                    full = _clip_to_frame(full, width, height)
                    confidence = float(round(min(1.0, 0.55 + 0.45 * float(_edge_length_score(full))), 3))
                    return DetectionResult(corners=full, method="contour", confidence=confidence)

        # ---- 3b. No clean 4-point approximation: rotated bounding box ----
        biggest = ranked[0]
        if float(cv2.contourArea(biggest)) >= MIN_DOCUMENT_AREA_RATIO * small_area:
            box = cv2.boxPoints(cv2.minAreaRect(biggest))
            quad = order_points(box)
            full = _clip_to_frame(quad / scale, width, height)
            confidence = float(round(min(1.0, 0.40 + 0.45 * float(_edge_length_score(full))), 3))
            return DetectionResult(corners=full, method="min-area-rect", confidence=confidence)

    # ---- 4. Fallback: 5% inner-padded full frame ----
    return _fallback_result(width, height)


def four_point_transform(image_rgb: np.ndarray, corners: Sequence[Sequence[float]]) -> np.ndarray:
    """Perspective-warp *image_rgb* so *corners* become a flat rectangle.

    The output size is the longest opposite-edge pair (width and height),
    which reproduces the physical page aspect ratio.  Areas outside the
    source quad are filled white (paper), never black.
    """
    rect = order_points(np.asarray(corners, dtype=np.float32))
    (tl, tr, br, bl) = rect

    width_top = float(np.linalg.norm(tr - tl))
    width_bottom = float(np.linalg.norm(br - bl))
    height_right = float(np.linalg.norm(br - tr))
    height_left = float(np.linalg.norm(bl - tl))

    max_width = max(1, int(round(max(width_top, width_bottom))))
    max_height = max(1, int(round(max(height_right, height_left))))

    dst = np.array(
        [[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(
        image_rgb,
        matrix,
        (max_width, max_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return warped


def corners_to_normalized(corners: np.ndarray, width: int, height: int) -> List[List[float]]:
    """Pixel corners -> normalized [x, y] pairs (0..1), TL/TR/BR/BL order."""
    norm = corners.astype(np.float64).copy()
    norm[:, 0] /= float(max(1, width - 1))
    norm[:, 1] /= float(max(1, height - 1))
    return [[round(float(x), 6), round(float(y), 6)] for x, y in norm]


def corners_from_normalized(
    normalized: Sequence[Sequence[float]],
    width: int,
    height: int,
) -> np.ndarray:
    """Normalized [x, y] pairs -> pixel corners, re-ordered for safety."""
    pts = np.asarray(normalized, dtype=np.float64).reshape(4, 2)
    if not np.all(np.isfinite(pts)) or np.any(pts < -0.02) or np.any(pts > 1.02):
        raise ValueError("corners must be 4 normalized [x, y] pairs within [0, 1]")
    pts[:, 0] = np.clip(pts[:, 0], 0.0, 1.0) * float(max(1, width - 1))
    pts[:, 1] = np.clip(pts[:, 1], 0.0, 1.0) * float(max(1, height - 1))
    return order_points(pts)


def fallback_corners(width: int, height: int) -> np.ndarray:
    """The 5%-inset full-frame quad used when detection fails."""
    res = detect_document_corners(np.zeros((height, width, 3), dtype=np.uint8) + 255)
    return res.corners  # type: ignore[return-value]
