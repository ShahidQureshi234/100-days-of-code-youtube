"""Image loading, EXIF handling and preview encoding helpers.

All file input goes through Pillow (broader format support than OpenCV's
imread, plus correct EXIF orientation for phone photos), then converts to
an RGB numpy array that OpenCV operates on.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps

# Guard against decompression bombs (PIL's own limit is ~178 MP which is
# generous; we tighten it a little for a web upload context).
Image.MAX_IMAGE_PIXELS = 120_000_000

#: Formats accepted for input (checked after EXIF transpose).
SUPPORTED_INPUT_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "TIFF", "PPM"}


class ImageLoadError(ValueError):
    """Raised when an input file cannot be decoded as a raster image."""


def load_rgb(path: str | Path) -> np.ndarray:
    """Load an image from *path* as an RGB uint8 numpy array (HxWx3).

    Handles EXIF orientation (phone photos are frequently stored rotated),
    rejects unsupported formats, and returns RGB channel order (not BGR)
    so the array round-trips with :func:`save_rgb`.
    """
    path = Path(path)
    if not path.is_file():
        raise ImageLoadError(f"file not found: {path}")

    try:
        with Image.open(path) as im:
            fmt = (im.format or "").upper()
            if fmt not in SUPPORTED_INPUT_FORMATS:
                raise ImageLoadError(f"unsupported image format: {fmt or 'unknown'}")
            # EXIF transpose rotates the pixel data into visual orientation.
            im = ImageOps.exif_transpose(im)
            if im.mode != "RGB":
                # Convert palette / greyscale / CMYK inputs to RGB.  An alpha
                # channel is composited over white (documents are paper).
                if im.mode in ("RGBA", "LA", "PA"):
                    background = Image.new("RGBA", im.size, (255, 255, 255, 255))
                    im = Image.alpha_composite(background, im.convert("RGBA"))
                im = im.convert("RGB")
            return np.asarray(im, dtype=np.uint8)
    except ImageLoadError:
        raise
    except Exception as exc:  # noqa: BLE001 - translate library errors
        raise ImageLoadError(f"cannot decode image: {exc}") from exc


def save_rgb(image: np.ndarray, path: str | Path, dpi: Optional[Tuple[int, int]] = None) -> None:
    """Save an RGB numpy array to *path* (format inferred from extension)."""
    pil = Image.fromarray(np.ascontiguousarray(image), mode="RGB")
    params = {"dpi": dpi} if dpi else {}
    pil.save(path, **params)


def rgb_to_bgr(image: np.ndarray) -> np.ndarray:
    """RGB -> BGR (OpenCV convention)."""
    return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)


def bgr_to_rgb(image: np.ndarray) -> np.ndarray:
    """BGR -> RGB."""
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def encode_preview(
    image_bgr: np.ndarray,
    max_edge: int = 1400,
    fmt: str = ".webp",
    quality: int = 82,
) -> bytes:
    """Encode a downscaled preview of *image_bgr* for the web UI.

    Returns the encoded file bytes (WebP by default: small and sharp).
    """
    h, w = image_bgr.shape[:2]
    scale = min(1.0, max_edge / float(max(h, w)))
    if scale < 1.0:
        small = cv2.resize(image_bgr, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_AREA)
    else:
        small = image_bgr

    if fmt == ".webp":
        ok, buf = cv2.imencode(".webp", small, [int(cv2.IMWRITE_WEBP_QUALITY), quality])
    elif fmt in (".jpg", ".jpeg"):
        ok, buf = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    elif fmt == ".png":
        ok, buf = cv2.imencode(".png", small)
    else:
        raise ValueError(f"unsupported preview format: {fmt}")
    if not ok:
        raise RuntimeError("preview encoding failed")
    return buf.tobytes()


def write_bytes(data: bytes, path: str | Path) -> Path:
    """Atomically write *data* to *path* (tmp file + rename)."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


def encode_tiff_g4(binary: np.ndarray, dpi: int = 300) -> bytes:
    """Encode a 0/255 uint8 binary image as a **CCITT Group 4** TIFF.

    Group 4 (T.6) is the same lossless monochrome codec industrial copiers
    embed in PDFs: it compresses text pages into tens of kilobytes.
    """
    if binary.ndim != 2:
        raise ValueError("binary image must be single-channel")
    pil = Image.fromarray(binary, mode="L")
    # dither=NONE keeps our exact 0/255 pixels -- no Floyd-Steinberg noise.
    mono = pil.convert("1", dither=Image.Dither.NONE)
    buf = io.BytesIO()
    mono.save(buf, format="TIFF", compression="group4", dpi=(dpi, dpi))
    return buf.getvalue()
