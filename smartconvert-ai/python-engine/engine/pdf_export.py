"""PDF assembly for all export strategies.

* **B&W mode**   -> every page is a CCITT Group 4 TIFF; ``img2pdf`` inserts
  the monochrome streams into the PDF *without recompression* (lossless
  passthrough, exactly how commercial scanners embed scans).
* **Color plain** -> JPEG (DCTDecode) or JPEG 2000 (JPXDecode) pages via
  ``img2pdf``, quality 70-75 per spec.
* **Color MRC**  -> :class:`engine.mrc_pdf.MrcPdfWriter` stacks a
  FlateDecode 1-bit text mask over the color layer on each page.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import img2pdf
import numpy as np
from PIL import Image, features as pil_features

from engine.mrc_pdf import MrcPage, MrcPdfWriter

#: Files produced by the process stage that exports consume.
PROCESSED_TIFF = "processed.tiff"
PROCESSED_JPEG = "processed.jpg"
PROCESSED_JP2 = "processed.jp2"
TEXT_MASK_PNG = "mask.png"
MRC_META = "mrc.json"


class ExportError(RuntimeError):
    """Raised when PDF assembly fails."""


def _img2pdf_bytes(paths: List[Path], dpi: int, title: str) -> bytes:
    """Assemble image files into one PDF honoring a fixed physical DPI."""
    if not paths:
        raise ExportError("no pages to export")
    layout = img2pdf.get_fixed_dpi_layout_fun((dpi, dpi))
    try:
        return img2pdf.convert(
            [str(p) for p in paths],
            layout_fun=layout,
            title=title or "SmartConvertAI Scan",
            producer="SmartConvertAI 1.0",
        )
    except Exception as exc:  # noqa: BLE001
        raise ExportError(f"img2pdf assembly failed: {exc}") from exc


def export_bw_pdf(tiff_paths: List[Path], out_path: Path, dpi: int, title: str) -> Dict:
    """B&W export: direct CCITT Group 4 monochrome streams (Mode A)."""
    data = _img2pdf_bytes(tiff_paths, dpi, title)
    out_path.write_bytes(data)
    return {"pdfPath": str(out_path), "pdfBytes": len(data), "pageCount": len(tiff_paths), "strategy": "ccitt-g4"}


def export_color_plain_pdf(image_paths: List[Path], out_path: Path, dpi: int, title: str) -> Dict:
    """Color export (single-layer): JPEG or JPEG 2000 pages via img2pdf."""
    data = _img2pdf_bytes(image_paths, dpi, title)
    out_path.write_bytes(data)
    return {"pdfPath": str(out_path), "pdfBytes": len(data), "pageCount": len(image_paths), "strategy": "color-plain"}


def _load_mrc_page(workdir: Path) -> MrcPage:
    """Rehydrate one processed color page into an :class:`MrcPage`."""
    meta_path = workdir / MRC_META
    if not meta_path.is_file():
        raise ExportError(f"missing {MRC_META} in {workdir}")
    meta = json.loads(meta_path.read_text())

    color_path = workdir / PROCESSED_JP2 if meta.get("filter") == "JPXDecode" else workdir / PROCESSED_JPEG
    if meta.get("filter") == "JPXDecode" and not color_path.is_file():
        color_path = workdir / PROCESSED_JPEG  # graceful degradation
    if not color_path.is_file():
        raise ExportError(f"missing processed color layer in {workdir}")

    mask_path = workdir / TEXT_MASK_PNG
    if not mask_path.is_file():
        raise ExportError(f"missing {TEXT_MASK_PNG} in {workdir}")

    with Image.open(mask_path) as mask_img:
        if mask_img.mode != "1":
            mask_img = mask_img.convert("1")
        mask_packed = mask_img.tobytes()  # MSB-first packed rows: PDF-ready
        mask_w, mask_h = mask_img.size

    return MrcPage(
        color_stream=color_path.read_bytes(),
        color_width=int(meta["colorWidth"]),
        color_height=int(meta["colorHeight"]),
        color_filter=meta.get("filter", "DCTDecode"),
        mask_packed=mask_packed,
        mask_width=mask_w,
        mask_height=mask_h,
        dpi=int(meta.get("dpi", 300)),
    )


def export_color_mrc_pdf(workdirs: List[Path], out_path: Path, title: str) -> Dict:
    """Color export (MRC): FlateDecode text mask over color layer per page."""
    writer = MrcPdfWriter(title=title or "SmartConvertAI Scan")
    for workdir in workdirs:
        writer.add_page(_load_mrc_page(Path(workdir)))
    data = writer.build()
    out_path.write_bytes(data)
    return {"pdfPath": str(out_path), "pdfBytes": len(data), "pageCount": len(workdirs), "strategy": "color-mrc"}


def export_pdf(
    workdirs: List[str | Path],
    mode: str,
    out_path: str | Path,
    title: str = "SmartConvertAI Scan",
    dpi: int = 300,
    color_codec: str = "jpeg",
    use_mrc: bool = True,
) -> Dict:
    """Dispatch an export by mode.  Entry point used by the CLI stage."""
    workdirs = [Path(w) for w in workdirs]
    out_path = Path(out_path)
    if not workdirs:
        raise ExportError("no pages to export")

    if mode == "bw":
        tiffs = []
        for wd in workdirs:
            tiff = wd / PROCESSED_TIFF
            if not tiff.is_file():
                raise ExportError(f"page not processed in B&W mode: {wd}")
            tiffs.append(tiff)
        return export_bw_pdf(tiffs, out_path, dpi, title)

    if mode == "color":
        if use_mrc:
            return export_color_mrc_pdf(workdirs, out_path, title)
        images = []
        for wd in workdirs:
            if color_codec == "jp2" and (wd / PROCESSED_JP2).is_file():
                images.append(wd / PROCESSED_JP2)
            else:
                jpeg = wd / PROCESSED_JPEG
                if not jpeg.is_file():
                    raise ExportError(f"page not processed in color mode: {wd}")
                images.append(jpeg)
        return export_color_plain_pdf(images, out_path, dpi, title)

    raise ExportError(f"unknown mode: {mode!r} (expected 'bw' or 'color')")


def jpeg2000_available() -> bool:
    """True when Pillow was built with OpenJPEG (JPEG 2000) support."""
    try:
        return bool(pil_features.check("jpg_2000"))
    except Exception:  # noqa: BLE001
        return False


def encode_jp2(rgb: np.ndarray, quality: int = 72) -> bytes:
    """Encode an RGB array as a JPEG 2000 codestream (PDF /JPXDecode)."""
    pil = Image.fromarray(np.ascontiguousarray(rgb), mode="RGB")
    # Map the 0-100 quality scale to a target compression *rate*
    # (bytes-per-byte; lower = smaller file).
    rate = max(0.02, (100.0 - float(quality)) / 100.0)
    buf = io.BytesIO()
    pil.save(buf, format="JPEG2000", quality_mode="rates", quality=rate, irreversible=True)
    return buf.getvalue()


def encode_jpeg(rgb: np.ndarray, quality: int = 72) -> bytes:
    """Encode an RGB array as JPEG bytes (PDF /DCTDecode)."""
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise ExportError("JPEG encoding failed")
    return buf.tobytes()
