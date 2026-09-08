/** POST /api/export -- assemble processed pages into one PDF (download).
 *
 * JSON body:
 *   { pageIds: string[], mode: "bw" | "color", filename?: string,
 *     dpi?: number, colorCodec?: "jpeg" | "jp2", useMrc?: boolean,
 *     sessionId?: string }
 *
 * Responds with the PDF byte stream (application/pdf).
 */

import { stat } from "node:fs/promises";
import { createReadStream } from "node:fs";
import path from "node:path";
import { NextRequest, NextResponse } from "next/server";
import { Readable } from "node:stream";
import { EngineError, runEngine } from "@/lib/engine";
import { dataRoot, getWorkspace, sweepExpiredWorkspaces } from "@/lib/registry";
import { sanitizeFilename } from "@/lib/validate";
import { recordExport } from "@/lib/db";
import type { ScanMode } from "@/lib/types";
import { randomUUID } from "node:crypto";
import { mkdir } from "node:fs/promises";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MODES: ScanMode[] = ["bw", "color"];

export async function POST(request: NextRequest) {
  void sweepExpiredWorkspaces();

  try {
    const body = (await request.json()) as {
      pageIds?: string[];
      mode?: string;
      filename?: string;
      dpi?: number;
      colorCodec?: string;
      useMrc?: boolean;
      sessionId?: string;
    };

    const mode = body.mode as ScanMode;
    if (!MODES.includes(mode)) {
      return NextResponse.json({ ok: false, error: "mode must be 'bw' or 'color'" }, { status: 400 });
    }
    if (!Array.isArray(body.pageIds) || body.pageIds.length === 0 || body.pageIds.length > 100) {
      return NextResponse.json({ ok: false, error: "pageIds must be a non-empty list (max 100)" }, { status: 400 });
    }

    const workdirs: string[] = [];
    for (const pageId of body.pageIds) {
      const workspace = await getWorkspace(String(pageId));
      if (!workspace) {
        return NextResponse.json(
          { ok: false, error: `unknown or expired page: ${pageId}` },
          { status: 404 }
        );
      }
      workdirs.push(workspace.dir);
    }

    const filename = sanitizeFilename(body.filename || "", `smartconvert-${mode}.pdf`);
    const exportDir = path.join(dataRoot(), "exports");
    await mkdir(exportDir, { recursive: true });
    const outPath = path.join(exportDir, `${randomUUID()}.pdf`);

    const args = [
      "--stage", "export",
      "--workdirs", JSON.stringify(workdirs),
      "--mode", mode,
      "--out", outPath,
      "--title", filename.replace(/\.pdf$/i, ""),
    ];
    const dpi = Number(body.dpi);
    if (Number.isFinite(dpi) && dpi >= 72 && dpi <= 600) args.push("--dpi", String(Math.round(dpi)));
    if (mode === "color") {
      args.push("--color-codec", body.colorCodec === "jp2" ? "jp2" : "jpeg");
      args.push(body.useMrc === false ? "--no-mrc" : "--mrc");
    }

    const { payload } = await runEngine(args);
    const info = await stat(outPath);

    if (body.sessionId && body.sessionId !== "offline") {
      await recordExport({
        sessionId: body.sessionId,
        filename,
        pdfBytes: info.size,
        pageCount: workdirs.length,
        mode,
        strategy: String(payload.strategy || ""),
      });
    }

    const stream = Readable.toWeb(createReadStream(outPath)) as ReadableStream;
    return new NextResponse(stream, {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Length": String(info.size),
        "Content-Disposition": `attachment; filename="${filename}"`,
        "X-Pdf-Bytes": String(info.size),
        "X-Export-Strategy": String(payload.strategy || ""),
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    if (err instanceof EngineError) {
      return NextResponse.json({ ok: false, error: err.message }, { status: 422 });
    }
    console.error("[api/export]", err);
    return NextResponse.json({ ok: false, error: "export failed" }, { status: 500 });
  }
}
