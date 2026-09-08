"""Minimal, dependency-free MRC (Mixed Raster Content) PDF writer.

Why a custom writer?  Standard image->PDF tools place each input image on
its own page.  An MRC page is *two stacked images on one page*:

    [background] color layer  -- /Filter /DCTDecode (JPEG) or /JPXDecode
                                 (JPEG 2000), quality 70-75, no text edges
                                 to smudge because text is not in this layer
    [foreground] 1-bit text   -- /Filter /FlateDecode /ImageMask true
                                 mask; razor-sharp glyph strokes painted in
                                 pure black over the background

The result matches industrial "text over image" scan layouts: photos keep
their color, text stays vector-crisp, and file sizes land in the 150-350 KB
per page budget.

Only the subset of ISO 32000 needed for this layout is emitted: catalog,
page tree, content streams, image XObjects, info dict, xref, trailer.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

PDF_HEADER = b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n"  # binary marker comment


@dataclass(frozen=True)
class MrcPage:
    """One stacked page: color layer + 1-bit text mask."""

    color_stream: bytes        # raw JPEG / JPEG2000 codestream bytes
    color_width: int
    color_height: int
    color_filter: str          # "DCTDecode" | "JPXDecode"
    mask_packed: bytes         # 1-bit rows, MSB-first, ink=1, byte-padded
    mask_width: int
    mask_height: int
    dpi: int = 300


@dataclass
class _Object:
    number: int
    body: bytes


class MrcPdfWriter:
    """Assemble :class:`MrcPage` items into a valid single PDF document."""

    def __init__(self, title: str = "SmartConvertAI Scan", producer: str = "SmartConvertAI 1.0") -> None:
        self.title = title
        self.producer = producer
        self.pages: List[MrcPage] = []

    def add_page(self, page: MrcPage) -> "MrcPdfWriter":
        if page.color_width <= 0 or page.color_height <= 0:
            raise ValueError("color layer dimensions must be positive")
        if page.mask_width <= 0 or page.mask_height <= 0:
            raise ValueError("mask dimensions must be positive")
        self.pages.append(page)
        return self

    # ------------------------------------------------------------------ #
    # Object serialization helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _dict_to_bytes(obj: dict) -> bytes:
        """Serialize a PDF dictionary (values may be bytes/str/int/refs)."""
        parts = []
        for key, value in obj.items():
            if isinstance(value, bytes):
                rendered = value
            elif isinstance(value, str):
                rendered = value.encode("latin-1", errors="replace")
            elif isinstance(value, bool):
                rendered = b"true" if value else b"false"
            elif isinstance(value, int):
                rendered = str(value).encode()
            else:  # list -> reference array or number array
                rendered = b"[" + b" ".join(str(v).encode() if not isinstance(v, bytes) else v for v in value) + b"]"
            parts.append(b"/" + key.encode() + b" " + rendered)
        return b"<< " + b" ".join(parts) + b" >>"

    @staticmethod
    def _stream_object(number: int, dict_extra: dict, data: bytes) -> bytes:
        head = f"{number} 0 obj\n".encode()
        dictionary = MrcPdfWriter._dict_to_bytes({**dict_extra, "Length": len(data)})
        return head + dictionary + b"\nstream\n" + data + b"\nendstream\nendobj\n"

    @staticmethod
    def _plain_object(number: int, body: bytes) -> bytes:
        return f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    @staticmethod
    def _escape_pdf_string(text: str) -> str:
        return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    # ------------------------------------------------------------------ #
    # Build
    # ------------------------------------------------------------------ #

    def build(self) -> bytes:
        if not self.pages:
            raise ValueError("cannot build a PDF with zero pages")

        n_pages = len(self.pages)
        # Object numbering:
        #   1 = catalog, 2 = pages tree
        #   per page i (0-based): 3 + i*4 .. 6 + i*4
        #       -> page dict, content stream, color image, mask image
        #   final object = info dict
        first_page_obj = 3
        info_number = first_page_obj + n_pages * 4

        chunks: List[bytes] = [PDF_HEADER]
        offsets = {0: 0}  # object number -> byte offset (0 is the free head)

        def emit(obj_number: int, payload: bytes) -> None:
            offsets[obj_number] = sum(len(c) for c in chunks)
            chunks.append(payload)

        # --- Catalog & page tree --------------------------------------- #
        kids = [f"{first_page_obj + i * 4} 0 R" for i in range(n_pages)]
        emit(1, self._plain_object(1, self._dict_to_bytes({"Type": b"/Catalog", "Pages": b"2 0 R"})))
        emit(
            2,
            self._plain_object(
                2,
                self._dict_to_bytes({"Type": b"/Pages", "Kids": [k.encode() for k in kids], "Count": n_pages}),
            ),
        )

        for index, page in enumerate(self.pages):
            page_num = first_page_obj + index * 4
            content_num = page_num + 1
            color_num = page_num + 2
            mask_num = page_num + 3

            # MediaBox in points: px * 72 / dpi.
            page_w_pt = page.color_width * 72.0 / float(page.dpi)
            page_h_pt = page.color_height * 72.0 / float(page.dpi)

            # --- Page dictionary --------------------------------------- #
            page_dict = self._dict_to_bytes(
                {
                    "Type": b"/Page",
                    "Parent": b"2 0 R",
                    "MediaBox": f"[0 0 {page_w_pt:.2f} {page_h_pt:.2f}]".encode(),
                    "Resources": self._dict_to_bytes(
                        {"XObject": self._dict_to_bytes({"Im0": f"{color_num} 0 R".encode(), "Im1": f"{mask_num} 0 R".encode()})}
                    ),
                    "Contents": f"{content_num} 0 R".encode(),
                }
            )
            emit(page_num, self._plain_object(page_num, page_dict))

            # --- Content stream: draw bg, then black text mask on top -- #
            # Images are drawn into the *unit square*, so the cm matrix must
            # scale them to the full PAGE SIZE IN POINTS (not pixels!).
            content = (
                f"q\n{page_w_pt:.2f} 0 0 {page_h_pt:.2f} 0 0 cm\n/Im0 Do\nQ\n"
                f"q\n0 0 0 rg\n{page_w_pt:.2f} 0 0 {page_h_pt:.2f} 0 0 cm\n/Im1 Do\nQ\n"
            ).encode()
            emit(content_num, self._stream_object(content_num, {}, content))

            # --- Color layer image XObject ----------------------------- #
            color_dict = {
                "Type": b"/XObject",
                "Subtype": b"/Image",
                "Width": page.color_width,
                "Height": page.color_height,
                "Filter": f"/{page.color_filter}".encode(),
            }
            if page.color_filter == "DCTDecode":
                color_dict["ColorSpace"] = b"/DeviceRGB"
                color_dict["BitsPerComponent"] = 8
            # JPXDecode streams are self-describing; extra entries optional.
            emit(color_num, self._stream_object(color_num, color_dict, page.color_stream))

            # --- 1-bit text mask XObject (FlateDecode) ------------------ #
            # ImageMask semantics (ISO 32000 8.9.6.4): decoded sample 0
            # paints the current fill colour, 1 leaves the page unchanged.
            # Our packed rows carry ink=1, hence /Decode [1 0] flips them
            # to 0 (= paint black) -- verified by the render-back test.
            compressed_mask = zlib.compress(page.mask_packed, 9)
            mask_dict = {
                "Type": b"/XObject",
                "Subtype": b"/Image",
                "Width": page.mask_width,
                "Height": page.mask_height,
                "ImageMask": True,
                "BitsPerComponent": 1,
                "Filter": b"/FlateDecode",
                "Decode": b"[1 0]",
            }
            emit(mask_num, self._stream_object(mask_num, mask_dict, compressed_mask))

        # --- Info dictionary -------------------------------------------- #
        now = datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ")
        info_dict = self._dict_to_bytes(
            {
                "Title": f"({self._escape_pdf_string(self.title)})".encode(),
                "Producer": f"({self._escape_pdf_string(self.producer)})".encode(),
                "CreationDate": now.encode(),
            }
        )
        emit(info_number, self._plain_object(info_number, info_dict))

        # --- Cross-reference table & trailer ---------------------------- #
        total_objects = info_number  # highest object number
        xref_offset = sum(len(c) for c in chunks)
        xref_lines = [b"xref", f"0 {total_objects + 1}".encode(), b"0000000000 65535 f \n"]
        for number in range(1, total_objects + 1):
            offset = offsets.get(number, 0)
            xref_lines.append(f"{offset:010d} 00000 n \n".encode())
        trailer = self._dict_to_bytes(
            {"Size": total_objects + 1, "Root": b"1 0 R", "Info": f"{info_number} 0 R".encode()}
        )
        chunks.append(b"\n".join(xref_lines))
        chunks.append(b"trailer\n" + trailer + b"\nstartxref\n" + str(xref_offset).encode() + b"\n%%EOF\n")

        return b"".join(chunks)
