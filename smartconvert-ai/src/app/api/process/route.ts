/** POST /api/process -- warp + filter one page.
 *
 * JSON body:
 *   { pageId, corners?: [{x,y} x 4], mode: "bw" | "color",
 *     settings?: {...}, dpi?: number, colorCodec?: "jpeg" | "jp2",
 *     sessionId?, originalName? }
 *
 * Returns the processed preview URL + compression stats.
 */

import { NextRequest, NextResponse } from "next/server";
import { EngineError, runEngine } from "@/lib/engine";
import { getWorkspace, sweepExpiredWorkspaces } from "@/lib/registry";
import { validateCorners, ValidationError } from "@/lib/validate";
import { upsertPage } from "@/lib/db";
import type { EngineSettings, ScanMode } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MODES: ScanMode[] = ["bw", "color"];

/** Translate UI settings to engine dataclass field names. */
function engineSettings(mode: ScanMode, raw: EngineSettings | undefined): Record<string, unknown> {
  if (!raw) return {};
  if (mode === "bw") {
    return {
      c: raw.bwC,
      block_size: raw.bwBlockSize,
      unsharp_alpha: raw.bwUnsharpAlpha,
      despeckle: raw.bwDespeckle,
    };
  }
  return {
    white_threshold: raw.colorWhiteThreshold,
    clahe_clip: raw.colorClaheClip,
    jpeg_quality: raw.colorQuality,
  };
}

function cleanSettings(settings: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(settings)) {
    if (value === undefined || value === null) continue;
    out[key] = value;
  }
  return out;
}

export async function POST(request: NextRequest) {
  void sweepExpiredWorkspaces();

  try {
    const body = (await request.json()) as {
      pageId?: string;
      corners?: unknown;
      mode?: string;
      settings?: EngineSettings;
      dpi?: number;
      colorCodec?: string;
      sessionId?: string;
      originalName?: string;
      originalBytes?: number;
    };

    if (!body.pageId) {
      return NextResponse.json({ ok: false, error: "missing pageId" }, { status: 400 });
    }
    const workspace = await getWorkspace(body.pageId);
    if (!workspace) {
      return NextResponse.json(
        { ok: false, error: "unknown or expired page -- upload it again" },
        { status: 404 }
      );
    }
    const mode = body.mode as ScanMode;
    if (!MODES.includes(mode)) {
      return NextResponse.json({ ok: false, error: "mode must be 'bw' or 'color'" }, { status: 400 });
    }
    const corners = validateCorners(body.corners);
    const dpi = Number(body.dpi);
    const codec = body.colorCodec === "jp2" ? "jp2" : "jpeg";

    const args = ["--stage", "process", "--workdir", workspace.dir, "--mode", mode];
    if (corners) args.push("--corners", JSON.stringify(corners.map((p) => [p.x, p.y])));
    const settings = cleanSettings(engineSettings(mode, body.settings));
    if (Object.keys(settings).length > 0) args.push("--settings", JSON.stringify(settings));
    if (Number.isFinite(dpi) && dpi >= 72 && dpi <= 600) args.push("--dpi", String(Math.round(dpi)));
    if (mode === "color") args.push("--color-codec", codec);

    const { payload, elapsedMs } = await runEngine(args);

    const stats = payload.stats as {
      originalBytes: number;
      processedBytes: number;
      reductionPct: number;
    };
    const cornersUsed = (payload.cornersUsed as number[][]).map(([x, y]) => ({ x, y }));

    // Persist page metadata (optional DB; sessionId may be "offline").
    if (body.sessionId && body.sessionId !== "offline") {
      await upsertPage({
        id: workspace.id,
        sessionId: body.sessionId,
        originalName: body.originalName || "scan",
        originalBytes: stats.originalBytes,
        width: Number(payload.outputWidth),
        height: Number(payload.outputHeight),
        mode,
        cornersJson: JSON.stringify(cornersUsed),
        autoDetected: Boolean(payload.cornersAuto),
        processedBytes: stats.processedBytes,
        processedFormat: String(payload.format),
        processingMs: elapsedMs,
        inkRatio: typeof payload.inkRatio === "number" ? payload.inkRatio : null,
      });
    }

    return NextResponse.json({
      ok: true,
      pageId: workspace.id,
      mode,
      urls: { preview: `/api/files/${workspace.id}/${String(payload.preview)}` },
      outputWidth: payload.outputWidth,
      outputHeight: payload.outputHeight,
      stats,
      inkRatio: payload.inkRatio ?? null,
      format: payload.format,
      cornersUsed,
      elapsedMs,
    });
  } catch (err) {
    if (err instanceof ValidationError) {
      return NextResponse.json({ ok: false, error: err.message }, { status: 400 });
    }
    if (err instanceof EngineError) {
      return NextResponse.json({ ok: false, error: err.message }, { status: 422 });
    }
    console.error("[api/process]", err);
    return NextResponse.json({ ok: false, error: "processing failed" }, { status: 500 });
  }
}
