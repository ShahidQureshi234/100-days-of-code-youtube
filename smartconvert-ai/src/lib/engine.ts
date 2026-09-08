/** Child-process bridge to the Python vision engine.
 *
 * The engine (python-engine/process_scan.py) speaks a strict JSON contract:
 * one JSON object on stdout, human-readable errors on stderr, non-zero exit
 * on failure.  We spawn it with an argument array (never a shell string),
 * enforce a hard timeout, and surface structured errors to the routes.
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

export const ENGINE_ROOT = path.join(process.cwd(), "python-engine");
export const ENGINE_SCRIPT = path.join(ENGINE_ROOT, "process_scan.py");

export class EngineError extends Error {
  readonly stderr: string;
  constructor(message: string, stderr = "") {
    super(message);
    this.name = "EngineError";
    this.stderr = stderr;
  }
}

/** Resolve the Python interpreter: env override -> project venv -> PATH. */
export function resolvePythonBin(): string {
  const candidates = [
    process.env.PYTHON_BIN,
    path.join(ENGINE_ROOT, ".venv", "bin", "python3"),
    "python3",
  ].filter(Boolean) as string[];

  for (const candidate of candidates) {
    // Absolute/relative paths must exist; bare names are resolved by PATH.
    if (candidate.includes(path.sep)) {
      if (existsSync(candidate)) return candidate;
    } else {
      return candidate;
    }
  }
  return "python3";
}

interface EngineRunResult {
  payload: Record<string, unknown>;
  elapsedMs: number;
}

/** Run one engine stage and parse its JSON output. Throws EngineError. */
export function runEngine(args: string[]): Promise<EngineRunResult> {
  const timeoutMs = Number(process.env.ENGINE_TIMEOUT_MS || 120_000);
  const started = Date.now();

  return new Promise<EngineRunResult>((resolve, reject) => {
    const child = spawn(resolvePythonBin(), [ENGINE_SCRIPT, ...args], {
      cwd: ENGINE_ROOT,
      env: { ...process.env, PYTHONUNBUFFERED: "1", PYTHONDONTWRITEBYTECODE: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new EngineError(`engine timed out after ${timeoutMs} ms`, stderr));
    }, timeoutMs);
    timer.unref?.();

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
      // Guard against a runaway engine printing gigabytes.
      if (stdout.length > 4_000_000) child.kill("SIGKILL");
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
      if (stderr.length > 200_000) stderr = stderr.slice(-100_000);
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(
        new EngineError(
          `cannot start python engine (${resolvePythonBin()}): ${err.message}. ` +
            "Run `npm run engine:setup` or set PYTHON_BIN in .env.local.",
          stderr
        )
      );
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      const elapsedMs = Date.now() - started;

      let payload: Record<string, unknown> | null = null;
      for (const line of stdout.trim().split("\n").reverse()) {
        try {
          const parsed = JSON.parse(line);
          if (parsed && typeof parsed === "object") {
            payload = parsed as Record<string, unknown>;
            break;
          }
        } catch {
          // not the JSON line -- keep scanning upwards
        }
      }

      if (code === 0 && payload && payload.ok === true) {
        resolve({ payload, elapsedMs });
        return;
      }
      const message =
        (payload && typeof payload.error === "string" && payload.error) ||
        (stderr.trim().split("\n").pop() ?? "") ||
        `engine exited with code ${code}`;
      reject(new EngineError(message, stderr));
    });
  });
}

let healthCache: { at: number; payload: Record<string, unknown> } | null = null;
const HEALTH_TTL_MS = 30_000;

/** Cached engine capability probe (used by /api/health). */
export async function engineHealth(force = false): Promise<Record<string, unknown>> {
  if (!force && healthCache && Date.now() - healthCache.at < HEALTH_TTL_MS) {
    return healthCache.payload;
  }
  try {
    const { payload } = await runEngine(["--stage", "health"]);
    healthCache = { at: Date.now(), payload };
    return payload;
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}
