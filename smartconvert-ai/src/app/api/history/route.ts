/** GET /api/history -- recent scan sessions (requires the DB to be enabled). */

import { NextResponse } from "next/server";
import { recentHistory } from "@/lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const history = await recentHistory(20);
  return NextResponse.json({ ok: true, ...history });
}
