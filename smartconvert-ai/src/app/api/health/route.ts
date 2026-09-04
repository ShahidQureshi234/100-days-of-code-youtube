/** GET /api/health -- engine + database + app status. */

import { NextResponse } from "next/server";
import { engineHealth } from "@/lib/engine";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const engine = await engineHealth();
  return NextResponse.json({
    ok: engine.ok === true,
    app: {
      name: process.env.APP_NAME || "SmartConvertAI",
      version: "1.0.0",
      node: process.version,
    },
    engine,
    database: { enabled: Boolean(process.env.DATABASE_URL) },
  });
}
