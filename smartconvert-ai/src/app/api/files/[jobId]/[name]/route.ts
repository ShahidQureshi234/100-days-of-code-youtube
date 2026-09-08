/** GET /api/files/[jobId]/[name] -- serve engine artifacts (previews, PDFs).
 *
 * Strictly whitelisted names, UUID-validated workspace ids, no traversal.
 */

import { readFile } from "node:fs/promises";
import { NextRequest, NextResponse } from "next/server";
import { artifactMime, artifactPath, getWorkspace, sweepExpiredWorkspaces } from "@/lib/registry";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _request: NextRequest,
  { params }: { params: { jobId: string; name: string } }
) {
  void sweepExpiredWorkspaces();

  const workspace = await getWorkspace(params.jobId);
  if (!workspace) {
    return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  }
  const filePath = artifactPath(workspace, params.name);
  if (!filePath) {
    return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  }
  try {
    const data = await readFile(filePath);
    const mime = artifactMime(params.name);
    const cacheable = mime.startsWith("image/");
    return new NextResponse(new Uint8Array(data), {
      status: 200,
      headers: {
        "Content-Type": mime,
        "Content-Length": String(data.length),
        "Cache-Control": cacheable ? "private, max-age=3600" : "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  }
}
