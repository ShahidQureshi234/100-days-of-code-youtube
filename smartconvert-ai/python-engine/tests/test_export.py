"""Export tests: PDF structure, MRC render-back, size budgets, multipage.

``pypdfium2`` renders the produced PDFs back to pixels -- the only honest
way to verify the custom MRC writer (mask polarity, stacking order, page
size) end to end.
"""

from __future__ import annotations

import io
import json
import zlib
from pathlib import Path

import numpy as np
import pytest

pypdfium2 = pytest.importorskip("pypdfium2")

from engine.color_mode import encode_text_mask_png
from engine.pipeline import stage_export, stage_process
from tests.conftest import make_skewed_photo


def _process_page(workdir: Path, photo: Path, mode: str, **kwargs) -> dict:
    # detect first (writes the original into the workspace)
    from engine.pipeline import stage_detect

    stage_detect(photo, workdir)
    return stage_process(workdir=workdir, corners=None, mode=mode, **kwargs)


def _render_first_page(pdf_path: Path, scale: float = 1.0) -> np.ndarray:
    doc = pypdfium2.PdfDocument(str(pdf_path))
    try:
        page = doc[0]
        bitmap = page.render(scale=scale)
        pil = bitmap.to_pil().convert("RGB")
        return np.asarray(pil)
    finally:
        doc.close()


# --------------------------------------------------------------------------- #
# Mode A export
# --------------------------------------------------------------------------- #
def test_bw_pdf_structure_and_size(skewed_photo, tmp_path):
    wd = tmp_path / "p1"
    wd.mkdir()
    result = _process_page(wd, skewed_photo, "bw")
    assert result["ok"] and result["format"] == "tiff-g4"

    export = stage_export([wd], "bw", tmp_path / "scan.pdf", dpi=300)
    assert export["ok"] and export["pageCount"] == 1

    data = (tmp_path / "scan.pdf").read_bytes()
    assert data[:5] == b"%PDF-"
    assert b"/CCITTFaxDecode" in data  # spec: CCITT Group 4 monochrome stream
    assert b"/Filter/DCTDecode" not in data  # no lossy layer in B&W mode
    assert len(data) < 200_000, f"B&W PDF too big: {len(data)}"


def test_bw_multipage_pdf(skewed_photo, tmp_path):
    dirs = []
    for i in range(2):
        wd = tmp_path / f"p{i}"
        wd.mkdir()
        _process_page(wd, skewed_photo, "bw")
        dirs.append(wd)

    export = stage_export(dirs, "bw", tmp_path / "multi.pdf", dpi=300)
    assert export["pageCount"] == 2

    doc = pypdfium2.PdfDocument(str(tmp_path / "multi.pdf"))
    try:
        assert len(doc) == 2
    finally:
        doc.close()


# --------------------------------------------------------------------------- #
# Mode B export (MRC)
# --------------------------------------------------------------------------- #
def test_color_mrc_pdf_renders_correctly(skewed_photo, tmp_path):
    """The critical render-back test for the custom MRC writer.

    Verifies: valid PDF, DCT color layer + Flate imagemask, white paper,
    visible black text, red logo preserved, and the 350 KB budget.
    """
    wd = tmp_path / "c1"
    wd.mkdir()
    result = _process_page(wd, skewed_photo, "color")
    assert result["ok"]

    export = stage_export([wd], "color", tmp_path / "color.pdf", dpi=300, use_mrc=True)
    assert export["ok"] and export["strategy"] == "color-mrc"

    data = (tmp_path / "color.pdf").read_bytes()
    assert data[:5] == b"%PDF-"
    assert b"/DCTDecode" in data          # color layer
    assert b"/FlateDecode" in data        # text mask
    assert b"/ImageMask" in data          # mask is a stencil
    assert len(data) < 350_000, f"color MRC PDF too big: {len(data)}"

    rendered = _render_first_page(tmp_path / "color.pdf", scale=1.5)
    h, w = rendered.shape[:2]

    # Paper margins must be (near) pure white -- mask must NOT invert.
    # Left rail at mid-page height: guaranteed blank paper on the fixture.
    margin = rendered[int(h * 0.30) : int(h * 0.35), int(w * 0.01) : int(w * 0.05)]
    assert margin.min() > 200, f"background dark/inverted: min={margin.min()}"

    # Some text pixels must be genuinely black.
    dark = (rendered.astype(int).sum(axis=2) < 240)
    assert dark.mean() > 0.01, "no dark text pixels rendered"

    # Logo hue survives (rendered RGB).
    red_rows, red_cols = np.where(
        (rendered[:, :, 0].astype(int) > rendered[:, :, 1].astype(int) + 25)
        & (rendered[:, :, 0].astype(int) > rendered[:, :, 2].astype(int) + 25)
    )
    assert len(red_rows) > 50, "logo color lost in MRC export"


def test_color_plain_pdf_fallback(skewed_photo, tmp_path):
    """Non-MRC color export (plain JPEG pages) also works (FR-008 alt)."""
    wd = tmp_path / "c2"
    wd.mkdir()
    _process_page(wd, skewed_photo, "color")

    export = stage_export([wd], "color", tmp_path / "plain.pdf", dpi=300, use_mrc=False)
    assert export["strategy"] == "color-plain"
    data = (tmp_path / "plain.pdf").read_bytes()
    assert data[:5] == b"%PDF-"
    assert b"/DCTDecode" in data


# --------------------------------------------------------------------------- #
# Custom writer internals
# --------------------------------------------------------------------------- #
def test_mrc_writer_xref_is_consistent(tmp_path):
    """The hand-built xref table must let a strict parser open the file."""
    from engine.mrc_pdf import MrcPage, MrcPdfWriter

    # 8x8 checkerboard-ish mask: ink where (x+y) odd.
    mask = np.zeros((8, 8), dtype=np.uint8)
    mask[1::2, 0::2] = 255
    mask[0::2, 1::2] = 255
    packed = encode_text_mask_png(mask)
    buf = io.BytesIO()
    packed.save(buf, format="PNG")
    from PIL import Image

    buf.seek(0)
    one_bit = Image.open(buf).convert("1")

    # 16x16 red JPEG color layer.
    import cv2

    layer = np.full((16, 16, 3), (40, 40, 220), np.uint8)
    ok, jpg = cv2.imencode(".jpg", layer)
    assert ok

    writer = MrcPdfWriter(title="Unit Test")
    writer.add_page(
        MrcPage(
            color_stream=jpg.tobytes(),
            color_width=16,
            color_height=16,
            color_filter="DCTDecode",
            mask_packed=one_bit.tobytes(),
            mask_width=8,
            mask_height=8,
            dpi=300,
        )
    )
    out = tmp_path / "unit.pdf"
    out.write_bytes(writer.build())

    doc = pypdfium2.PdfDocument(str(out))
    try:
        assert len(doc) == 1
        rendered = np.asarray(doc[0].render(scale=1).to_pil().convert("RGB"))
        assert rendered.size > 0
        # Mask ink (checkerboard) must render as dark pixels over red bg.
        dark = rendered.astype(int).sum(axis=2) < 300
        assert dark.mean() > 0.1, "checkerboard mask did not render"
    finally:
        doc.close()


def test_mrc_writer_requires_pages():
    from engine.mrc_pdf import MrcPdfWriter

    with pytest.raises(ValueError):
        MrcPdfWriter().build()
