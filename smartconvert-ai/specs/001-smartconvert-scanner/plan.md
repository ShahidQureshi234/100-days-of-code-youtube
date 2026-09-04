# Implementation Plan: SmartConvertAI Document Scanner

**Branch**: `001-smartconvert-scanner` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

## Summary

Full-stack web app: Next.js 14 (App Router) + Tailwind + Framer Motion + Lucide frontend; Next API routes spawning a Python/OpenCV child-process engine; Prisma + SQLite persistence; img2pdf (CCITT G4 direct embedding) + a custom minimal PDF writer (MRC text-mask stacking) for exports.

## Technical Context

**Language/Version**: TypeScript 5 (Node 22), Python 3.11
**Primary Dependencies**: next@14.2, react@18, tailwindcss@3.4, framer-motion@11, lucide-react; opencv-python-headless, numpy, Pillow, img2pdf (Python engine); prisma@5, @prisma/client
**Storage**: SQLite via Prisma (default; `DATABASE_URL` swappable to PostgreSQL); job artifacts in OS temp workspace
**Testing**: pytest (Python engine: synthetic skewed documents, shadow gradients, size budgets, PDF structural checks via pypdfium2); end-to-end curl tests against API routes
**Target Platform**: Any Node 18.17+ host with Python 3.9+ (Linux/macOS/WSL)
**Project Type**: web-app (single deployable)
**Performance Goals**: B&W page ≤ 80 KB, color page ≤ 350 KB, 2-page flow < 30 s
**Constraints**: Engine child-process timeout 120 s; uploads ≤ 25 MB; no shell interpolation (spawn args arrays only)
**Scale/Scope**: 1 project, ~30 files, 4 API routes + 6 UI components

## Constitution Check

- **Library-First / Engine Isolation**: ✓ The vision engine is a standalone Python package (`python-engine/`) with a JSON CLI contract — usable without the web app, independently testable.
- **CLI Interface**: ✓ `process_scan.py` is a text-in/text-out CLI (args → JSON on stdout, errors to stderr, non-zero exit).
- **Test-First**: ✓ Engine tests written alongside engine code and run in this session before integration; synthetic fixtures encode the spec's acceptance criteria (SC-001…SC-004).
- **Security by Default**: ✓ Magic-byte validation, size caps, path-sanitized file serving, child-process timeouts, no eval/shell, artifacts isolated per-UUID workspace, no secrets in client code.

## Project Structure

```
smartconvert-ai/
├── README.md                     # Full setup, architecture, API docs
├── package.json                  # Deps + scripts (dev/build/engine:setup/engine:test/db:push)
├── next.config.mjs               # ESLint bypass for build, security headers
├── tsconfig.json / tailwind.config.ts / postcss.config.mjs
├── .env.example                  # DATABASE_URL, PYTHON_BIN, MAX_UPLOAD_MB, ENGINE_TIMEOUT_MS…
├── .gitignore
├── prisma/schema.prisma          # ScanSession / ScanPage / ExportJob
├── specs/001-smartconvert-scanner/   # SDD artifacts (this folder)
├── python-engine/                # Standalone CV engine (library-first)
│   ├── requirements.txt / requirements-dev.txt
│   ├── process_scan.py           # JSON CLI: detect | process | export | health
│   ├── engine/
│   │   ├── detection.py          # Canny→contours→quad, order corners, warpPerspective, 5% fallback
│   │   ├── bw_mode.py            # Illumination close(21×21) → unsharp(0.5) → adaptiveThreshold(15, C=10)
│   │   ├── color_mode.py         # LAB, L>220→white, CLAHE, text-mask extraction
│   │   ├── mrc_pdf.py            # Custom minimal PDF writer: DCTDecode layer + FlateDecode imagemask
│   │   ├── pdf_export.py         # img2pdf (G4/JP2/JPEG) + MRC assembly
│   │   ├── pipeline.py           # Orchestration + stats
│   │   └── imaging.py            # PIL loading, EXIF transpose, preview encoding
│   └── tests/                    # pytest suite + synthetic fixture generator
└── src/
    ├── app/                      # Next.js App Router
    │   ├── layout.tsx / page.tsx / globals.css
    │   └── api/
    │       ├── detect/route.ts   # POST upload → corners + preview (FR-001..004)
    │       ├── process/route.ts  # POST pageId+corners+mode → processed page + stats (FR-005..008)
    │       ├── export/route.ts   # POST pageIds+mode → PDF download (FR-009)
    │       ├── files/[jobId]/[name]/route.ts  # GET sanitized artifact serving
    │       ├── health/route.ts   # GET engine+DB status
    │       └── history/route.ts  # GET recent sessions (FR-011)
    ├── components/               # UploadZone, CropAdjuster, ModeSwitcher, SettingsPanel,
    │   │                         # ResultViewer, ExportBar, ScanWorkbench
    └── lib/                      # engine.ts (spawn bridge), registry.ts (workspaces),
                                  # db.ts (optional Prisma), types.ts, validate.ts
```

**Structure Decision**: Single Next.js app with an out-of-process Python engine (spawned per request) — keeps the web tier pure TS/Node while the CV pipeline stays a first-class, independently-testable Python library. Exports assemble on the Python side to guarantee byte-exact PDF streams.

## Complexity Tracking

| Area | Complexity | Mitigation |
|---|---|---|
| Quad detection robustness | Medium | Downscale-detect-upscale, area/convexity filters, deterministic 5% fallback |
| CCITT G4 embedding | Low | img2pdf direct-insertion (no recompression) |
| MRC layered PDF | High | Custom minimal writer + pypdfium2 render-back tests; plain-JPEG fallback path |
| State across requests | Medium | Disk-keyed UUID workspaces + in-memory registry + graceful DB-optional design |
