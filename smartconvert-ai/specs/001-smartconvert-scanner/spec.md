# Feature Specification: SmartConvertAI Document Scanner

**Feature Branch**: `001-smartconvert-scanner`
**Created**: 2026-09-04
**Status**: Approved
**Input**: User description: "Web-based document scanner (SmartConvertAI) replicating industrial Xerox/Canon scanning machines — upload images, auto-detect borders, crop/de-skew, Xerox-style compression filters, export ultra-light PDFs (KB) with crystal-clear sharp text."

## User Scenarios & Testing _(mandatory)_

### User Story 1 - Scan a photographed document to a tiny B&W PDF (Priority: P1)

A user photographs a printed document with their phone (skewed perspective, shadows). They upload the JPEG, the app auto-detects the document borders, de-skews to a flat top-down view, and applies the Xerox B&W filter (pure black text, pure white background, zero shadow). They export a multi-page PDF where each page is 20–80 KB with razor-sharp text.

**Why this priority**: This is the core Xerox-machine replication and the primary value proposition — industrial-grade B&W scanning output in the browser.

**Independent Test**: Upload a skewed phone photo → auto-detect corners → process in B&W mode → export PDF → assert PDF page size < 80 KB for a typical text page and text strokes are pure black on pure white.

**Acceptance Scenarios**:
1. **Given** a JPEG photo containing a document at an angle, **When** the user uploads it, **Then** the system detects 4 document corners and shows them as an adjustable overlay.
2. **Given** detected corners, **When** the user confirms, **Then** the image is perspective-warped to a flat top-down view.
3. **Given** a warped page with lighting gradient/shadow, **When** B&W mode is applied, **Then** the background is 100% white with no grey shadow and text is 100% black.
4. **Given** processed B&W pages, **When** the user exports, **Then** a PDF is produced with CCITT Group 4 monochrome streams (20–80 KB/page).
5. **Given** a photo where no document edges are detectable, **When** detection runs, **Then** the system falls back to a 5% inner-padded auto-crop.

### User Story 2 - Preserve color/graphics with smart cleanup (Priority: P2)

A user scans a page containing a logo, charts, or photos. They pick Smart Color mode: background yellowing/greys pushed to pure white, visual elements preserved with CLAHE contrast, text stays sharp. Export lands at 150–350 KB/page using a text-mask + color-layer (MRC-style) layout.

**Why this priority**: Extends the scanner beyond text documents to mixed graphical content while keeping sizes small.

**Independent Test**: Upload a page with a colored logo → process in Smart Color mode → export PDF → assert background near-white, logo colors preserved, page < 350 KB.

**Acceptance Scenarios**:
1. **Given** a warped color page, **When** Smart Color is applied, **Then** light greys (L > 220) in the background become pure white.
2. **Given** colored visual elements, **When** processing completes, **Then** their detail/contrast is enhanced via CLAHE without destroying text sharpness.
3. **Given** a color page, **When** exported, **Then** text is laid down as a FlateDecode monochrome mask over a JPEG (DCTDecode/JPXDecode) color layer.

### User Story 3 - Adjust the crop before processing (Priority: P3)

A user wants manual control: they drag the four corner handles of the crop overlay, reset to auto-detected corners, or use the full image.

**Why this priority**: Auto-detection is usually right but not always; manual override builds trust and handles edge cases.

**Independent Test**: Move corners → process → assert the exported page geometry matches the moved corners.

**Acceptance Scenarios**:
1. **Given** the crop overlay, **When** the user drags any corner handle, **Then** the quad polygon updates in real time.
2. **Given** modified corners, **When** "Reset to auto" is clicked, **Then** corners snap back to the detected values.
3. **Given** any state, **When** "Use full image" is clicked, **Then** corners move to the image edges.

### User Story 4 - Track scan history (Priority: P4)

A user can review their recent scan sessions (files, sizes, modes, export jobs) persisted in a database.

**Why this priority**: Product-grade ergonomics; makes the app feel like a real appliance with a job log.

**Independent Test**: Complete a scan + export → reload the history panel → assert the session and export job appear with correct byte counts.

**Acceptance Scenarios**:
1. **Given** a processed page, **When** processing completes, **Then** a ScanPage record persists with metadata.
2. **Given** an export, **When** the download starts, **Then** an ExportJob record persists with PDF size and page count.

## Requirements _(mandatory)_

### Functional Requirements

- **FR-001**: System MUST accept image uploads (JPEG/PNG/WebP/BMP/TIFF) up to 25 MB via drag & drop or file picker, validated by magic bytes.
- **FR-002**: System MUST auto-detect document borders using Grayscale → Gaussian Blur (5×5, σ=0) → Canny (50, 150) → findContours → approxPolyDP, and produce an ordered 4-corner quad.
- **FR-003**: System MUST apply getPerspectiveTransform + warpPerspective for a flat top-down view.
- **FR-004**: System MUST fall back to a 5% inner-padded crop when no quad is confidently detected.
- **FR-005 (Mode A)**: System MUST remove illumination gradients via morphological closing (21×21), lock strokes with unsharp masking (α=0.5), and binarize with adaptiveThreshold (Gaussian C, blockSize=15, C=10).
- **FR-006 (Mode A)**: System MUST encode pages as 1-bit CCITT Group 4 streams inside the exported PDF.
- **FR-007 (Mode B)**: System MUST convert to LAB, push light greys (L > 220) to pure white, apply CLAHE while maintaining text sharpness.
- **FR-008 (Mode B)**: System MUST export with a FlateDecode text mask layered over a 70–75% quality color layer (JPEG DCTDecode or JPEG2000 JPXDecode).
- **FR-009**: System MUST support multi-page documents (upload N images → 1 PDF).
- **FR-010**: System MUST expose manual corner adjustment with reset/full-image options.
- **FR-011**: System MUST persist scan sessions, pages, and export jobs via Prisma ORM (SQLite default, PostgreSQL-ready).
- **FR-012**: System MUST show before/after previews and compression statistics (original vs processed bytes, reduction %).

### Key Entities

- **ScanSession**: one user visit/working set; has many ScanPages and ExportJobs.
- **ScanPage**: one uploaded image → detection → processing artifact set (original, warped, processed, previews) + metadata.
- **ExportJob**: one PDF assembly event (page refs, byte size, filename, mode).

## Success Criteria _(mandatory)_

### Measurable Outcomes

- **SC-001**: A typical 300 DPI text page exports in B&W mode at ≤ 80 KB (target 20–80 KB).
- **SC-002**: A typical color page with graphics exports in Smart Color mode at ≤ 350 KB (target 150–350 KB).
- **SC-003**: B&W output contains only pure black and pure white pixels (0% grey background).
- **SC-004**: Document corner detection succeeds (or safely falls back) on ≥ 90% of synthetic skewed-document test photos.
- **SC-005**: The end-to-end flow (upload → detect → process → export) completes for a 2-page document in under 30 seconds on commodity hardware.

## Assumptions

- Users upload photographs/scans of documents; the document is the dominant bright rectangular region in frame (standard assumption for scanner apps).
- Mode is selected per document (global), mirroring how a physical Xerox machine works; per-page mixing is out of scope for v1.
- HEIC inputs are out of scope for v1 (documented); users convert to JPEG/PNG first.
- Single-server deployment; job artifacts live in a runtime temp workspace (production hardening would move this to object storage + Redis registry).
