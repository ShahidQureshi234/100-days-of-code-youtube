"""Pipeline orchestration: detect -> process -> export stages.

Each stage takes plain paths/dicts and returns a JSON-serializable dict so
``process_scan.py`` (and therefore any host process) can consume the output
without importing anything but this package's public names.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import img2pdf
import numpy as np
import PIL
from PIL import Image

from engine import __version__
from engine.bw_mode import BwSettings, process_bw
from engine.color_mode import ColorSettings, process_color, encode_text_mask_png
from engine.detection import (
    detect_document_corners,
    four_point_transform,
    corners_to_normalized,
    corners_from_normalized,
)
from engine.imaging import (
    ImageLoadError,
    encode_preview,
    encode_tiff_g4,
    load_rgb,
    write_bytes,
)
from engine import pdf_export
from engine.pdf_export import (
    MRC_META,
    PROCESSED_JPEG,
    PROCESSED_JP2,
    PROCESSED_TIFF,
    TEXT_MASK_PNG,
    ExportError,
    encode_jpeg,
    encode_jp2,
    jpeg2000_available,
)

#: Artifact file names (referenced by the web API when serving previews).
ORIGINAL_PNG = "original.png"
ORIGINAL_JPG = "original.jpg"
PREVIEW_ORIGINAL = "preview_original.jpg"
PREVIEW_DETECT = "preview_detect.jpg"
PREVIEW_PROCESSED = "preview_processed.webp"

ALLOWED_MODES = ("bw", "color")


class PipelineError(RuntimeError):
    """Raised for invalid stage arguments or processing failures."""


# --------------------------------------------------------------------------- #
# Stage: detect
# --------------------------------------------------------------------------- #
def stage_detect(input_path: str | Path, workdir: str | Path, preview_max_edge: int = 1600) -> Dict[str, Any]:
    """Load an upload, auto-detect the document quad, emit previews.

    Returns normalized corners (TL, TR, BR, BL; x/y in 0..1) plus a warped
    preview so the UI can show the expected de-skewed result immediately.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    image = load_rgb(input_path)  # EXIF-corrected RGB
    height, width = image.shape[:2]
    if width < 100 or height < 100:
        raise PipelineError(f"image too small to be a document scan: {width}x{height}")

    # Keep a canonical copy inside the workspace.  JPEG inputs stay JPEG
    # (quality 98 is visually lossless here); others become PNG.
    src = Path(input_path)
    if src.suffix.lower() in (".jpg", ".jpeg"):
        Image.fromarray(image).save(workdir / ORIGINAL_JPG, quality=98)
        original_name = ORIGINAL_JPG
    else:
        Image.fromarray(image).save(workdir / ORIGINAL_PNG)
        original_name = ORIGINAL_PNG

    # Downscaled original preview drives the crop-adjuster UI.
    write_bytes(encode_preview(cv2.cvtColor(image, cv2.COLOR_RGB2BGR), preview_max_edge, ".jpg", 85), workdir / PREVIEW_ORIGINAL)

    detection = detect_document_corners(image)
    warped = four_point_transform(image, detection.corners)
    write_bytes(encode_preview(cv2.cvtColor(warped, cv2.COLOR_RGB2BGR), preview_max_edge, ".jpg", 85), workdir / PREVIEW_DETECT)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "ok": True,
        "stage": "detect",
        "original": original_name,
        "previewOriginal": PREVIEW_ORIGINAL,
        "previewDetect": PREVIEW_DETECT,
        "width": width,
        "height": height,
        "corners": corners_to_normalized(detection.corners, width, height),
        "cornersAuto": detection.is_auto,
        "method": detection.method,
        "confidence": detection.confidence,
        "elapsedMs": elapsed_ms,
    }


# --------------------------------------------------------------------------- #
# Stage: process
# --------------------------------------------------------------------------- #
def _find_original(workdir: Path) -> Path:
    for name in (ORIGINAL_JPG, ORIGINAL_PNG):
        candidate = workdir / name
        if candidate.is_file():
            return candidate
    raise PipelineError(f"no original image found in {workdir}")


def _bw_settings_from(settings: Dict[str, Any]) -> BwSettings:
    known = BwSettings.__dataclass_fields__.keys()
    return BwSettings(**{k: v for k, v in settings.items() if k in known})


def _color_settings_from(settings: Dict[str, Any]) -> ColorSettings:
    known = ColorSettings.__dataclass_fields__.keys()
    return ColorSettings(**{k: v for k, v in settings.items() if k in known})


def stage_process(
    workdir: str | Path,
    corners: Optional[Sequence[Sequence[float]]],
    mode: str,
    settings: Optional[Dict[str, Any]] = None,
    dpi: int = 300,
    color_codec: str = "jpeg",
    keep_warped: bool = True,
) -> Dict[str, Any]:
    """Warp (with *corners* or auto-detection) and run the chosen mode."""
    if mode not in ALLOWED_MODES:
        raise PipelineError(f"unknown mode {mode!r}; expected one of {ALLOWED_MODES}")
    workdir = Path(workdir)
    settings = dict(settings or {})

    started = time.perf_counter()
    original = _find_original(workdir)
    original_bytes = original.stat().st_size
    image = load_rgb(original)
    height, width = image.shape[:2]

    # ---- Warp (manual corners take precedence; else auto-detect) ---- #
    if corners is not None:
        try:
            pixel_corners = corners_from_normalized(corners, width, height)
            used_auto = False
        except Exception as exc:  # noqa: BLE001
            raise PipelineError(f"invalid corners: {exc}") from exc
    else:
        detection = detect_document_corners(image)
        pixel_corners = detection.corners
        used_auto = True
    warped = four_point_transform(image, pixel_corners)

    if keep_warped:
        # Full-resolution warped master (PNG, lossless) for reprocessing.
        Image.fromarray(warped).save(workdir / "warped.png")

    warp_ms = int((time.perf_counter() - started) * 1000)

    # ---- Mode pipelines ---- #
    if mode == "bw":
        cfg = _bw_settings_from(settings)
        result = process_bw(warped, cfg)
        tiff_bytes = encode_tiff_g4(result.binary, dpi=dpi)
        write_bytes(tiff_bytes, workdir / PROCESSED_TIFF)
        preview_bgr = cv2.cvtColor(result.binary, cv2.COLOR_GRAY2BGR)
        preview_bytes = encode_preview(preview_bgr, 1400, ".webp", 85)
        write_bytes(preview_bytes, workdir / PREVIEW_PROCESSED)
        processed_bytes = len(tiff_bytes)
        extra: Dict[str, Any] = {"inkRatio": result.ink_ratio, "format": "tiff-g4"}
    else:
        cfg = _color_settings_from(settings)
        result = process_color(warped, cfg)

        color_stream = encode_jpeg(result.color_rgb, quality=cfg.jpeg_quality)
        write_bytes(color_stream, workdir / PROCESSED_JPEG)
        text_filter = "DCTDecode"

        if color_codec == "jp2" and jpeg2000_available():
            try:
                jp2_bytes = encode_jp2(result.color_rgb, quality=cfg.jpeg_quality)
                write_bytes(jp2_bytes, workdir / PROCESSED_JP2)
                text_filter = "JPXDecode"
            except Exception:  # noqa: BLE001 - JPEG 2000 optional
                text_filter = "DCTDecode"

        encode_text_mask_png(result.text_mask).save(workdir / TEXT_MASK_PNG, optimize=True)
        mask_bytes = (workdir / TEXT_MASK_PNG).stat().st_size

        (workdir / MRC_META).write_text(
            json.dumps(
                {
                    "colorWidth": int(result.color_rgb.shape[1]),
                    "colorHeight": int(result.color_rgb.shape[0]),
                    "filter": text_filter,
                    "quality": cfg.jpeg_quality,
                    "dpi": int(dpi),
                }
            )
        )
        preview_bytes = encode_preview(cv2.cvtColor(result.color_rgb, cv2.COLOR_RGB2BGR), 1400, ".webp", 85)
        write_bytes(preview_bytes, workdir / PREVIEW_PROCESSED)
        processed_bytes = len(color_stream) + mask_bytes
        extra = {"inkRatio": result.ink_ratio, "format": f"{text_filter.lower()}+flate-mask", "maskBytes": mask_bytes}

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    reduction = round(100.0 * (1.0 - processed_bytes / float(max(1, original_bytes))), 1)

    return {
        "ok": True,
        "stage": "process",
        "mode": mode,
        "cornersUsed": corners_to_normalized(pixel_corners, width, height),
        "cornersAuto": used_auto,
        "processed": PROCESSED_TIFF if mode == "bw" else PROCESSED_JPEG,
        "preview": PREVIEW_PROCESSED,
        "outputWidth": int(result.binary.shape[1]) if mode == "bw" else int(result.color_rgb.shape[1]),
        "outputHeight": int(result.binary.shape[0]) if mode == "bw" else int(result.color_rgb.shape[0]),
        "stats": {
            "originalBytes": original_bytes,
            "processedBytes": processed_bytes,
            "reductionPct": reduction,
        },
        "elapsedMs": elapsed_ms,
        "warpMs": warp_ms,
        **extra,
    }


# --------------------------------------------------------------------------- #
# Stage: export
# --------------------------------------------------------------------------- #
def stage_export(
    workdirs: Sequence[str | Path],
    mode: str,
    out_path: str | Path,
    title: str = "SmartConvertAI Scan",
    dpi: int = 300,
    color_codec: str = "jpeg",
    use_mrc: bool = True,
) -> Dict[str, Any]:
    """Assemble processed pages into a single downloadable PDF."""
    started = time.perf_counter()
    result = pdf_export.export_pdf(
        workdirs=list(workdirs),
        mode=mode,
        out_path=out_path,
        title=title,
        dpi=dpi,
        color_codec=color_codec,
        use_mrc=use_mrc,
    )
    result.update({"ok": True, "stage": "export", "elapsedMs": int((time.perf_counter() - started) * 1000), "engineVersion": __version__})
    return result


# --------------------------------------------------------------------------- #
# Stage: health
# --------------------------------------------------------------------------- #
def stage_health() -> Dict[str, Any]:
    """Engine capability report (used by /api/health)."""
    return {
        "ok": True,
        "stage": "health",
        "engineVersion": __version__,
        "opencv": cv2.__version__,
        "numpy": np.__version__,
        "pillow": PIL.__version__,
        "img2pdf": getattr(img2pdf, "__version__", "installed"),
        "jpeg2000": jpeg2000_available(),
    }


__all__ = [
    "PipelineError",
    "ImageLoadError",
    "ExportError",
    "stage_detect",
    "stage_process",
    "stage_export",
    "stage_health",
]
