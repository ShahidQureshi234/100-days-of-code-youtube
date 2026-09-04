/** Optional Prisma access -- the app degrades gracefully without a DB.
 *
 * If @prisma/client has not been generated (or DATABASE_URL is unset) every
 * helper returns null/[] instead of throwing, so scanning and exporting keep
 * working; only history tracking is disabled.
 */

import type { ScanMode } from "./types";

type PrismaLike = {
  scanSession: {
    create: (args: unknown) => Promise<{ id: string }>;
    findMany: (args: unknown) => Promise<unknown[]>;
    count: (args?: unknown) => Promise<number>;
  };
  scanPage: {
    upsert: (args: unknown) => Promise<unknown>;
  };
  exportJob: {
    create: (args: unknown) => Promise<unknown>;
  };
  $disconnect: () => Promise<void>;
};

let cached: PrismaLike | null | undefined;

async function getDb(): Promise<PrismaLike | null> {
  if (cached !== undefined) return cached;
  if (!process.env.DATABASE_URL) {
    cached = null;
    return cached;
  }
  try {
    // Dynamic import so a missing generated client cannot break the route.
    const mod = await import("@prisma/client");
    const PrismaClient = (mod as { PrismaClient?: new () => PrismaLike }).PrismaClient;
    if (!PrismaClient) throw new Error("PrismaClient not generated (run `npm run db:generate`)");
    cached = new PrismaClient() as PrismaLike;
    return cached;
  } catch {
    console.warn("[smartconvert] database disabled:", "Prisma client unavailable");
    cached = null;
    return cached;
  }
}

function hashIp(value: string | null): string | null {
  if (!value) return null;
  // Cheap non-reversible bucketing (crypto sha256 would need node:crypto import here).
  let h1 = 0x811c9dc5;
  for (let i = 0; i < value.length; i++) {
    h1 ^= value.charCodeAt(i);
    h1 = Math.imul(h1, 0x01000193) >>> 0;
  }
  return `fnv1a-${h1.toString(16)}`;
}

export async function createSession(userAgent: string | null, ip: string | null): Promise<string | null> {
  const db = await getDb();
  if (!db) return null;
  try {
    const session = await db.scanSession.create({
      data: { userAgent: userAgent ?? null, ipHash: hashIp(ip) },
    });
    return session.id;
  } catch (err) {
    console.warn("[smartconvert] createSession failed:", err);
    return null;
  }
}

export interface PageRecord {
  id: string;
  sessionId: string;
  originalName: string;
  originalBytes: number;
  width: number;
  height: number;
  mode: ScanMode;
  cornersJson: string;
  autoDetected: boolean;
  processedBytes?: number | null;
  processedFormat?: string | null;
  processingMs?: number | null;
  inkRatio?: number | null;
}

export async function upsertPage(record: PageRecord): Promise<void> {
  const db = await getDb();
  if (!db) return;
  try {
    await db.scanPage.upsert({
      where: { id: record.id },
      create: {
        id: record.id,
        sessionId: record.sessionId,
        originalName: record.originalName.slice(0, 200),
        originalBytes: record.originalBytes,
        width: record.width,
        height: record.height,
        mode: record.mode,
        cornersJson: record.cornersJson,
        autoDetected: record.autoDetected,
        processedBytes: record.processedBytes ?? null,
        processedFormat: record.processedFormat ?? null,
        processingMs: record.processingMs ?? null,
        inkRatio: record.inkRatio ?? null,
      },
      update: {
        mode: record.mode,
        cornersJson: record.cornersJson,
        autoDetected: record.autoDetected,
        processedBytes: record.processedBytes ?? null,
        processedFormat: record.processedFormat ?? null,
        processingMs: record.processingMs ?? null,
        inkRatio: record.inkRatio ?? null,
      },
    });
  } catch (err) {
    console.warn("[smartconvert] upsertPage failed:", err);
  }
}

export interface ExportRecord {
  sessionId: string;
  filename: string;
  pdfBytes: number;
  pageCount: number;
  mode: ScanMode;
  strategy: string;
}

export async function recordExport(record: ExportRecord): Promise<void> {
  const db = await getDb();
  if (!db) return;
  try {
    await db.exportJob.create({ data: { ...record } });
  } catch (err) {
    console.warn("[smartconvert] recordExport failed:", err);
  }
}

export interface HistoryResult {
  sessions: {
    id: string;
    createdAt: string;
    pages: {
      id: string;
      originalName: string;
      mode: string;
      originalBytes: number;
      processedBytes: number | null;
      processingMs: number | null;
    }[];
    exports: { filename: string; pdfBytes: number; pageCount: number; strategy: string | null }[];
  }[];
  dbEnabled: boolean;
}

export async function recentHistory(limit = 20): Promise<HistoryResult> {
  const db = await getDb();
  if (!db) return { sessions: [], dbEnabled: false };
  try {
    const rows = await db.scanSession.findMany({
      orderBy: { createdAt: "desc" },
      take: limit,
      include: {
        pages: { orderBy: { createdAt: "asc" } },
        exports: { orderBy: { createdAt: "desc" } },
      },
    });
    return {
      dbEnabled: true,
      sessions: rows.map((row) => {
        const r = row as {
          id: string;
          createdAt: { toISOString(): string };
          pages: {
            id: string;
            originalName: string;
            mode: string;
            originalBytes: number;
            processedBytes: number | null;
            processingMs: number | null;
          }[];
          exports: { filename: string; pdfBytes: number; pageCount: number; strategy: string | null }[];
        };
        return {
          id: r.id,
          createdAt: r.createdAt.toISOString(),
          pages: r.pages,
          exports: r.exports,
        };
      }),
    };
  } catch (err) {
    console.warn("[smartconvert] recentHistory failed:", err);
    return { sessions: [], dbEnabled: true };
  }
}
