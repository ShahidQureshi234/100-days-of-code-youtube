"""SmartConvertAI vision engine.

A standalone, library-first computer-vision pipeline that replicates
industrial Xerox/Canon document scanning:

  * Edge detection + perspective de-skew (Canny -> contours -> warpPerspective)
  * Mode A: True black & white (illumination map, unsharp mask, adaptive
    threshold, CCITT Group 4 monochrome encoding)
  * Mode B: Smart color preservation (LAB whitening, CLAHE, MRC-style
    text mask + color layer PDF layout)

The package is intentionally framework-free: `process_scan.py` exposes a
JSON-over-stdout CLI that any host process (here: Next.js API routes) can
spawn.  Every module is independently importable and unit-testable.
"""

__version__ = "1.0.0"

from engine.imaging import load_rgb, encode_preview  # noqa: F401
from engine.detection import detect_document_corners, order_points, four_point_transform  # noqa: F401
