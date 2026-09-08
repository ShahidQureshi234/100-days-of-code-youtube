# Tasks: SmartConvertAI Document Scanner

**Input**: Design documents from `specs/001-smartconvert-scanner/`
**Prerequisites**: spec.md (required), plan.md (required)
**Organization**: Phased; engine before web; tests before integration.

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Project scaffold: package.json, tsconfig, tailwind, postcss, next.config, .env.example, .gitignore
- [x] T002 Prisma schema (ScanSession/ScanPage/ExportJob) + db push + client generation

## Phase 2: Foundational (Python CV Engine — blocking for all stories)

- [x] T003 `engine/imaging.py`: PIL load, EXIF transpose, RGB conversion, preview encoder (WebP/JPEG)
- [x] T004 `engine/detection.py`: grayscale→blur(5×5,σ=0)→Canny(50,150)→contours→approxPolyDP→ordered quad; warpPerspective; 5% fallback (FR-002/003/004)
- [x] T005 `engine/bw_mode.py`: closing(21×21) illumination map, unsharp(α=0.5), adaptiveThreshold(Gaussian C, 15, C=10), speck cleanup, TIFF G4 encode (FR-005/006)
- [x] T006 `engine/color_mode.py`: LAB, CLAHE(clip 2.0), L>220→white soft ramp, text-mask extraction (FR-007)
- [x] T007 `engine/mrc_pdf.py`: minimal PDF writer — DCTDecode/JPXDecode color layer + FlateDecode 1-bit imagemask stacking (FR-008)
- [x] T008 `engine/pdf_export.py`: img2pdf multipage G4/JPEG export + MRC assembly + metadata
- [x] T009 `engine/pipeline.py` + `process_scan.py` CLI: detect/process/export/health stages, JSON contract
- [x] T010 `tests/`: synthetic skewed-document fixture generator + pytest suite (SC-001..SC-004, FR checks) — ALL PASSING

## Phase 3: User Story 1 — B&W Xerox Flow (P1, MVP)

- [x] T011 `lib/engine.ts`: python resolution, spawn, JSON parse, timeout, typed results
- [x] T012 `lib/registry.ts`: UUID workspaces, artifact path registry, TTL cleanup
- [x] T013 `lib/validate.ts`: magic-byte sniffing, size caps, filename sanitize
- [x] T014 API `POST /api/detect`: upload → corners + warped preview (FR-001..004)
- [x] T015 API `POST /api/process`: corners+mode+settings → processed artifacts + stats + DB record (FR-005/006, FR-012)
- [x] T016 API `POST /api/export`: pages → PDF stream download + ExportJob record (FR-009)
- [x] T017 API `GET /api/files/[jobId]/[name]`: sanitized artifact serving
- [x] T018 End-to-end curl test: detect → process → export → PDF assertions

## Phase 4: User Story 2 — Smart Color Flow (P2)

- [x] T019 Color mode API integration (settings: whiteThreshold, claheClip, quality, codec)
- [x] T020 MRC export path through API with plain-JPEG fallback

## Phase 5: User Story 3 — Crop Adjuster (P3)

- [x] T021 `CropAdjuster` canvas component: draggable handles, polygon overlay, reset/full-image/auto actions
- [x] T022 Normalized corner contract between UI ⇄ engine

## Phase 6: User Story 4 — UI & History (P4)

- [x] T023 `UploadZone`: drag & drop, multi-file, validation, thumbnails, removal
- [x] T024 `ModeSwitcher` + `SettingsPanel`: B&W/Color toggle with live parameter sliders
- [x] T025 `ResultViewer` + `ExportBar`: before/after, stats cards, export/download
- [x] T026 `ScanWorkbench` orchestrator: page state machine, batch progress, error states
- [x] T027 `layout.tsx`/`page.tsx`/`globals.css`: dark professional theme, Framer Motion transitions
- [x] T028 API `GET /api/history` + history rendering (FR-011)
- [x] T029 `GET /api/health`: engine + DB status
- [x] T030 README.md: setup, architecture, pipeline docs, API reference, troubleshooting

## Phase 7: Verification

- [x] T031 Python engine test suite green (size budgets, purity, detection, PDF structure via pypdfium2)
- [x] T032 Next.js dev server boots; all API routes exercised; live preview verified
