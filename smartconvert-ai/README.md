# SmartConvertAI 📄⚡

**Web-based document scanner that replicates industrial Xerox/Canon scanning machines.** Upload photos of documents, auto-detect borders, de-skew with perspective correction, apply Xerox-style compression filters, and export **ultra-light PDFs (KB, not MB)** with crystal-clear, sharp text.

| Mode | Target | Codec / layout | Typical result* |
|---|---|---|---|
| **Mode A — B&W Xerox** | 20–80 KB/page, 100% sharp text, 0% grey shadow | CCITT Group 4 monochrome | **9 KB** (99% smaller) |
| **Mode B — Smart Color (MRC)** | 150–350 KB/page, colors preserved, yellowing removed | FlateDecode text mask over DCTDecode/JPXDecode color layer | **148 KB** (80% smaller) |

\* measured on the synthetic 300-DPI text-page fixture in `python-engine/tests` (755 KB skewed JPEG input).

---

## Architecture

```
┌─────────────────────────── Browser ────────────────────────────┐
│  Next.js 14 App Router · React 18 · Tailwind · Framer Motion   │
│  UploadZone → CropAdjuster (draggable quad) → ModeSwitcher     │
│  → SettingsPanel (live tuning) → ResultViewer → Export/Download│
└───────────────┬────────────────────────────────────────────────┘
                │ fetch (JSON / multipart / PDF stream)
┌───────────────▼───────────── Next.js API routes ───────────────┐
│ POST /api/detect   upload → corner detection (Canny pipeline)  │
│ POST /api/process  warp + filter page, stats, DB record        │
│ POST /api/export   assemble multi-page PDF (download)          │
│ GET  /api/files/…  sanitized artifact serving                  │
│ GET  /api/health · /api/history                                 │
└───────────────┬────────────────────────────────────────────────┘
                │ spawn (args array, JSON on stdout, hard timeout)
┌───────────────▼──────────── python-engine/ ────────────────────┐
│ engine/detection.py  Grayscale → GaussianBlur(5×5,σ=0) →       │
│                      Canny(50,150) → findContours →            │
│                      approxPolyDP → warpPerspective            │
│                      (fallback: 5% inner-padded auto-crop)     │
│ engine/bw_mode.py    closing(21×21) illumination map →         │
│                      unsharp(α=0.5) → adaptiveThreshold        │
│                      (Gaussian C, blockSize=15, C=10) →        │
│                      despeckle → TIFF CCITT G4                 │
│ engine/color_mode.py LAB → illumination flatten (max-filter) → │
│                      CLAHE → L>220→white (+chroma neutralize)  │
│                      → text-mask extraction (dark+low-chroma)  │
│ engine/mrc_pdf.py    minimal PDF writer: color layer +         │
│                      1-bit FlateDecode ImageMask stacked/page  │
│ engine/pdf_export.py img2pdf (G4/DCT/JPX passthrough) + MRC    │
│ process_scan.py      JSON CLI: detect|process|export|health    │
└────────────────────────────────────────────────────────────────┘
                │ Prisma (optional)
        ┌───────▼───────────────────────────────┐
        │ SQLite/PostgreSQL: ScanSession,       │
        │ ScanPage, ExportJob (scan history)    │
        └───────────────────────────────────────┘
```

**Design decisions**
- The vision engine is a **standalone Python package** with a strict JSON CLI — testable without the web app, swappable by any host.
- B&W pages embed the **raw CCITT G4 stream** into the PDF (no recompression) — exactly what commercial scanners emit.
- Color mode uses a **true MRC layout**: a 1-bit FlateDecode *image mask* carries the text (vector-crisp, immune to JPEG artifacts) over a 70–75% quality color layer carrying photos/logos.
- The DB is **optional by design**: set `DATABASE_URL` and history tracking activates; without it the scanner keeps working.

---

## Quick start

### Prerequisites
- Node.js ≥ 18.17 (tested on 22)
- Python ≥ 3.9 with pip (tested on 3.11)
- ~25 MB free for dependencies

### 1. Install & run

```bash
cd smartconvert-ai
npm install

# Python engine dependencies (pick one):
npm run engine:setup            # creates python-engine/.venv (recommended)
# or: pip install -r python-engine/requirements.txt   (system-wide)

# (Optional) enable scan history — needs https access to binaries.prisma.sh
npm run db:setup

cp .env.example .env.local      # adjust PYTHON_BIN etc. if needed
npm run dev                     # http://localhost:3000
```

If you installed the engine system-wide instead of the venv, set
`PYTHON_BIN="python3"` in `.env.local` (the bridge auto-detects the venv first).

### 2. Verify

```bash
npm run engine:test             # 23 pytest cases: detection, purity, budgets, PDF render-back
curl localhost:3000/api/health  # engine + app status
```

---

## Using the scanner

1. **Upload** — drag & drop one or more photos (JPEG/PNG/WebP/BMP/TIFF, ≤ 25 MB each, up to 20 pages).
2. **Adjust crop** — corners are auto-detected (Canny → contours); drag the TL/TR/BR/BL handles if needed, or use *Reset to auto* / *Full image*. A live badge shows the detection method and confidence; when nothing is detectable the engine falls back to a 5%-inset auto-crop.
3. **Choose a mode** — *B&W Xerox* (~20–80 KB/page) or *Smart Color* (~150–350 KB/page). Advanced settings expose every pipeline knob (threshold C, block size, unsharp α, white threshold, CLAHE clip, quality, DPI, codec).
4. **Process pages** — warp + filter runs per page with live status badges.
5. **Export PDF** — all processed pages assemble into one PDF; the download starts automatically with size + strategy feedback.
6. **History** (when DB enabled) — recent sessions, page counts and export sizes at the bottom of the page.

---

## API reference

| Route | Method | Body | Returns |
|---|---|---|---|
| `/api/detect` | POST | multipart `file` (+ header `X-Session-Id`) | `{pageId, corners[4], method, confidence, urls{…}}` |
| `/api/process` | POST | JSON `{pageId, corners?, mode, settings?, dpi?, colorCodec?}` | `{urls.preview, stats{originalBytes, processedBytes, reductionPct}, format, …}` |
| `/api/export` | POST | JSON `{pageIds[], mode, filename?, useMrc?}` | `application/pdf` stream (+ `X-Pdf-Bytes`, `X-Export-Strategy`) |
| `/api/files/{jobId}/{name}` | GET | — | artifact (whitelisted names only) |
| `/api/health` | GET | — | engine + database status |
| `/api/history` | GET | — | recent sessions (requires DB) |

**Engine CLI** (used by the routes, usable standalone):

```bash
python3 python-engine/process_scan.py --stage health
python3 python-engine/process_scan.py --stage detect  --input photo.jpg --workdir /tmp/job
python3 python-engine/process_scan.py --stage process --workdir /tmp/job --mode bw \
    --corners '[[0.1,0.1],[0.9,0.1],[0.9,0.9],[0.1,0.9]]'
python3 python-engine/process_scan.py --stage export --workdirs '["/tmp/job"]' \
    --mode color --mrc --out scan.pdf --title "My Scan"
```

---

## Security & robustness

- **Magic-byte validation** — uploads are sniffed, never trusted by extension; 25 MB cap.
- **No shell** — the Python engine is spawned with an argument array (no interpolation), with a hard `ENGINE_TIMEOUT_MS` kill.
- **Artifact isolation** — every page lives in a UUID workspace under the data root; `/api/files` serves only a fixed whitelist of artifact names (path traversal returns 404).
- **Graceful degradation** — missing DB, missing JPEG 2000 codec, engine fallbacks are all handled; the UI shows a toast instead of failing.
- **Workspace GC** — job directories are swept after 2 hours.

## Project layout

```
smartconvert-ai/
├── prisma/schema.prisma        # ScanSession / ScanPage / ExportJob
├── python-engine/              # standalone CV engine (see above)
│   ├── engine/  ·  process_scan.py  ·  tests/ (23 pytest cases)
├── specs/001-smartconvert-scanner/   # SDD artifacts (spec → plan → tasks)
└── src/
    ├── app/                    # layout, page, globals.css
    │   └── api/                # detect · process · export · files · health · history
    ├── components/             # ScanWorkbench, UploadZone, CropAdjuster,
    │                           # ModeSwitcher, SettingsPanel, ResultViewer, HistoryPanel
    └── lib/                    # engine bridge, registry, validation, db, types
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/api/health` reports engine error | Run `npm run engine:setup`, or set `PYTHON_BIN` in `.env.local` |
| `prisma generate` network error | Some networks block `binaries.prisma.sh`; retry or use a mirror via `PRISMA_ENGINES_MIRROR` |
| History panel missing | DB disabled — run `npm run db:setup` and restart |
| Detection badge shows *fallback* | Photo lacks a clear paper/background contrast; drag the corners manually |

## License

MIT — built as a complete, production-pattern reference implementation of an industrial-style document scanning pipeline.
