/** POST /api/detect -- upload an image, auto-detect the document quad.
 *
 * multipart/form-data: file=<image>
 * Optional header: X-Session-Id (reuses an existing scan session).
 *
 * Returns the page id, normalized corners (TL,TR,BR,BL), preview URLs.
 */

import { writeFile } from "node:fs/promises";
import path from "node:path";
import { NextRequest, NextResponse } from "next/server";
import { EngineError, runEngine } from "@/lib/engine";
import { createWorkspace, sweepExpiredWorkspaces } from "@/lib/registry";
import { validateUpload, ValidationError } from "@/lib/validate";
import { createSession } from "@/lib/db";
import type { Point } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function fileUrl(pageId: string, name: string): string {
  return `/api/files/${pageId}/${name}`;
}

export async function POST(request: NextRequest) {
  void sweepExpiredWorkspaces(); // fire & forget GC

  try {
    const form = await request.formData();
    const file = form.get("file");
    if (!(file instanceof File)) {
      return NextResponse.json({ ok: false, error: "missing 'file' field" }, { status: 400 });
    }

    const buffer = Buffer.from(await file.arrayBuffer());
    const extension = validateUpload(buffer); // magic bytes + size cap

    const workspace = await createWorkspace();
    const uploadPath = path.join(workspace.dir, `upload${extension}`);
    await writeFile(uploadPath, buffer);

    const engineArgs = ["--stage", "detect", "--input", uploadPath, "--workdir", workspace.dir];
    const { payload, elapsedMs } = await runEngine(engineArgs);

    // Session tracking (optional DB).
    const sessionId =
      request.headers.get("x-session-id") ||
      (await createSession(request.headers.get("user-agent"), request.headers.get("x-forwarded-for"))) ||
      "offline";

    const corners = (payload.corners as number[][]).map(([x, y]) => ({ x, y } as Point));
    const original = String(payload.original);
    const previewOriginal = String(payload.previewOriginal);
    const previewDetect = String(payload.previewDetect);

    return NextResponse.json(
      {
        ok: true,
        pageId: workspace.id,
        sessionId,
        width: payload.width,
        height: payload.height,
        corners,
        cornersAuto: Boolean(payload.cornersAuto),
        method: payload.method,
        confidence: payload.confidence,
        urls: {
          original: fileUrl(workspace.id, original),
          previewOriginal: fileUrl(workspace.id, previewOriginal),
          previewDetect: fileUrl(workspace.id, previewDetect),
        },
        elapsedMs: elapsedMs,
      },
      { headers: { "X-Session-Id": sessionId } }
    );
  } catch (err) {
    if (err instanceof ValidationError) {
      return NextResponse.json({ ok: false, error: err.message }, { status: 415 });
    }
    if (err instanceof EngineError) {
      return NextResponse.json({ ok: false, error: err.message }, { status: 422 });
    }
    console.error("[api/detect]", err);
    return NextResponse.json({ ok: false, error: "upload processing failed" }, { status: 500 });
  }
}
