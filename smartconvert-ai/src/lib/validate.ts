/** Upload validation: magic-byte sniffing, size caps, filename hygiene. */

export const SUPPORTED_MIME_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/bmp",
  "image/tiff",
] as const;

export type SupportedMime = (typeof SUPPORTED_MIME_TYPES)[number];

export const MIME_EXTENSIONS: Record<SupportedMime, string> = {
  "image/jpeg": ".jpg",
  "image/png": ".png",
  "image/webp": ".webp",
  "image/bmp": ".bmp",
  "image/tiff": ".tiff",
};

export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}

export function maxUploadBytes(): number {
  const mb = Number(process.env.MAX_UPLOAD_MB || 25);
  return Math.max(1, Number.isFinite(mb) ? mb : 25) * 1024 * 1024;
}

/** Sniff the true format from magic bytes -- never trust the declared type. */
export function sniffMime(buffer: Buffer): SupportedMime | null {
  if (buffer.length < 12) return null;
  if (buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff) return "image/jpeg";
  if (buffer[0] === 0x89 && buffer[1] === 0x50 && buffer[2] === 0x4e && buffer[3] === 0x47) return "image/png";
  if (
    buffer.toString("ascii", 0, 4) === "RIFF" &&
    buffer.toString("ascii", 8, 12) === "WEBP"
  )
    return "image/webp";
  if (buffer[0] === 0x42 && buffer[1] === 0x4d) return "image/bmp";
  if (
    (buffer[0] === 0x49 && buffer[1] === 0x49 && buffer[2] === 0x2a && buffer[3] === 0x00) ||
    (buffer[0] === 0x4d && buffer[1] === 0x4d && buffer[2] === 0x00 && buffer[3] === 0x2a)
  )
    return "image/tiff";
  return null;
}

/** Full upload validation; returns the safe extension for storage. */
export function validateUpload(buffer: Buffer): string {
  if (buffer.length === 0) throw new ValidationError("empty file");
  if (buffer.length > maxUploadBytes()) {
    throw new ValidationError(`file exceeds the ${Math.round(maxUploadBytes() / 1048576)} MB upload limit`);
  }
  const mime = sniffMime(buffer);
  if (!mime) {
    throw new ValidationError(
      "unsupported file type -- upload a JPEG, PNG, WebP, BMP or TIFF image"
    );
  }
  return MIME_EXTENSIONS[mime];
}

/** Sanitize a user-provided filename for Content-Disposition. */
export function sanitizeFilename(name: string, fallback = "smartconvert-scan.pdf"): string {
  const cleaned = (name || "")
    .replace(/[\r\n"\\]/g, "")
    .replace(/[^A-Za-z0-9._() -]/g, "_")
    .replace(/^\.+/, "")
    .trim();
  if (!cleaned || cleaned === "." || cleaned === "..") return fallback;
  return cleaned.slice(0, 120);
}

/** Validate a normalized corner quad from the client. */
export function validateCorners(value: unknown): { x: number; y: number }[] | null {
  if (value === null || value === undefined) return null;
  if (!Array.isArray(value) || value.length !== 4) return null;
  const corners: { x: number; y: number }[] = [];
  for (const point of value) {
    if (typeof point !== "object" || point === null) return null;
    const { x, y } = point as { x?: unknown; y?: unknown };
    if (typeof x !== "number" || typeof y !== "number" || !Number.isFinite(x) || !Number.isFinite(y)) {
      return null;
    }
    if (x < 0 || x > 1 || y < 0 || y > 1) return null;
    corners.push({ x, y });
  }
  return corners;
}
