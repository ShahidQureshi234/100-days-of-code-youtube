/** Runtime workspace registry.
 *
 * Every uploaded page gets an isolated, UUID-named directory under the data
 * root (env DATA_DIR, else <os.tmpdir>/smartconvert-ai).  The engine writes
 * its artifacts there; /api/files serves them back with strict name
 * sanitization.  Workspaces are garbage-collected after TTL_MS.
 *
 * The registry is disk-backed (not just an in-memory map) so the dev server
 * can reload (hot reload, crash) without orphaning live UIs.
 */

import { mkdir, readdir, rm, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** Artifact names the engine produces (and the only ones we will serve). */
export const ALLOWED_ARTIFACTS = new Set([
  "original.png",
  "original.jpg",
  "warped.png",
  "preview_original.jpg",
  "preview_detect.jpg",
  "preview_processed.webp",
  "processed.tiff",
  "processed.jpg",
  "processed.jp2",
  "mask.png",
  "mrc.json",
  "scan.pdf",
]);

export const TTL_MS = 2 * 60 * 60 * 1000; // 2 hours

export function dataRoot(): string {
  return process.env.DATA_DIR && process.env.DATA_DIR.trim().length > 0
    ? path.resolve(process.env.DATA_DIR)
    : path.join(os.tmpdir(), "smartconvert-ai");
}

export interface Workspace {
  id: string;
  dir: string;
}

/** Create + register a fresh workspace. */
export async function createWorkspace(): Promise<Workspace> {
  const id = randomUUID();
  const dir = path.join(dataRoot(), id);
  await mkdir(dir, { recursive: true });
  return { id, dir };
}

/** Look up a workspace by id (valid UUID + directory must exist). */
export async function getWorkspace(id: string): Promise<Workspace | null> {
  if (typeof id !== "string" || !UUID_RE.test(id)) return null;
  const dir = path.join(dataRoot(), id);
  if (!existsSync(dir)) return null;
  return { id, dir };
}

/** Resolve a safe artifact path inside a workspace (no traversal). */
export function artifactPath(workspace: Workspace, name: string): string | null {
  if (typeof name !== "string" || !ALLOWED_ARTIFACTS.has(name)) return null;
  return path.join(workspace.dir, name);
}

/** Best-effort GC of expired workspaces (called on API activity). */
let lastGc = 0;
export async function sweepExpiredWorkspaces(force = false): Promise<void> {
  const now = Date.now();
  if (!force && now - lastGc < 10 * 60 * 1000) return; // at most every 10 min
  lastGc = now;
  try {
    const root = dataRoot();
    if (!existsSync(root)) return;
    for (const entry of await readdir(root)) {
      if (!UUID_RE.test(entry)) continue;
      const dir = path.join(root, entry);
      try {
        const info = await stat(dir);
        if (now - info.mtimeMs > TTL_MS) {
          await rm(dir, { recursive: true, force: true });
        }
      } catch {
        // raced with another sweep -- ignore
      }
    }
  } catch {
    // GC must never break a request
  }
}

/**mime type by artifact extension (for /api/files). */
export function artifactMime(name: string): string {
  if (name.endsWith(".png")) return "image/png";
  if (name.endsWith(".jpg") || name.endsWith(".jpeg")) return "image/jpeg";
  if (name.endsWith(".webp")) return "image/webp";
  if (name.endsWith(".tiff")) return "image/tiff";
  if (name.endsWith(".jp2")) return "image/jp2";
  if (name.endsWith(".json")) return "application/json";
  if (name.endsWith(".pdf")) return "application/pdf";
  return "application/octet-stream";
}
