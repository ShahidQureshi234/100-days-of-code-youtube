/** Shared types between API routes and client components. */

export type ScanMode = "bw" | "color";

export interface Point {
  x: number; // 0..1 normalized against image width
  y: number; // 0..1 normalized against image height
}

/** Tuning knobs -- intentionally mirrors the Python engine's dataclasses. */
export interface EngineSettings {
  // Mode A (B&W)
  bwC?: number; // adaptive threshold constant (default 10)
  bwBlockSize?: number; // adaptive threshold block size (default 15)
  bwUnsharpAlpha?: number; // unsharp strength (default 0.5)
  bwDespeckle?: boolean; // remove dust specks (default true)
  // Mode B (Color)
  colorWhiteThreshold?: number; // L above this -> pure white (default 220)
  colorClaheClip?: number; // CLAHE clip limit (default 2.0)
  colorQuality?: number; // color layer quality 0-100 (default 72)
}

export interface DetectSuccess {
  ok: true;
  pageId: string;
  sessionId: string;
  width: number;
  height: number;
  corners: Point[];
  cornersAuto: boolean;
  method: string; // contour | min-area-rect | fallback
  confidence: number;
  urls: {
    original: string;
    previewOriginal: string;
    previewDetect: string;
  };
  elapsedMs: number;
}

export interface ProcessSuccess {
  ok: true;
  pageId: string;
  mode: ScanMode;
  urls: { preview: string };
  outputWidth: number;
  outputHeight: number;
  stats: {
    originalBytes: number;
    processedBytes: number;
    reductionPct: number;
  };
  inkRatio: number;
  format: string;
  elapsedMs: number;
}

export interface HistorySession {
  id: string;
  createdAt: string;
  pageCount: number;
  exportCount: number;
  totalPdfBytes: number;
  pages: {
    id: string;
    originalName: string;
    mode: string;
    originalBytes: number;
    processedBytes: number | null;
    processingMs: number | null;
  }[];
}

export interface ApiError {
  ok: false;
  error: string;
}

export type DetectResponse = DetectSuccess | ApiError;
export type ProcessResponse = ProcessSuccess | ApiError;
