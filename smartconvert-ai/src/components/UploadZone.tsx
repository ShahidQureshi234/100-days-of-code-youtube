"use client";

/** Drag & drop multi-file upload zone. */

import { useCallback, useRef, useState } from "react";
import { motion } from "framer-motion";
import { FileImage, UploadCloud } from "lucide-react";
import { formatBytes } from "@/lib/format";

const ACCEPTED = ["image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"];

export function clientValidate(file: File, maxMb = 25): string | null {
  if (!ACCEPTED.includes(file.type)) {
    return `${file.name}: unsupported type (${file.type || "unknown"})`;
  }
  if (file.size > maxMb * 1024 * 1024) {
    return `${file.name}: ${formatBytes(file.size)} exceeds the ${maxMb} MB limit`;
  }
  if (file.size === 0) {
    return `${file.name}: empty file`;
  }
  return null;
}

export default function UploadZone({
  onFiles,
  disabled,
  maxPages,
  pageCount,
}: {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
  maxPages?: number;
  pageCount?: number;
}) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const full = maxPages !== undefined && pageCount !== undefined && pageCount >= maxPages;

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setDragging(false);
      if (disabled || full) return;
      const files = Array.from(event.dataTransfer.files ?? []).filter((f) => f.type.startsWith("image/"));
      if (files.length > 0) onFiles(files);
    },
    [disabled, full, onFiles]
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled && !full) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`relative rounded-2xl border-2 border-dashed transition-colors ${
        dragging
          ? "border-accent-400 bg-accent-500/10"
          : full
            ? "border-surface-700 bg-surface-900/40 opacity-60"
            : "border-surface-600 bg-surface-900/40 hover:border-accent-500/50"
      }`}
    >
      <button
        type="button"
        disabled={disabled || full}
        onClick={() => inputRef.current?.click()}
        className="flex w-full flex-col items-center gap-3 px-6 py-10 text-center focus:outline-none"
        aria-label="Upload document images"
      >
        <span
          className={`flex h-14 w-14 items-center justify-center rounded-2xl ${
            dragging ? "bg-accent-500/20 text-accent-300" : "bg-surface-800 text-slate-400"
          }`}
        >
          {dragging ? <UploadCloud className="h-7 w-7" /> : <FileImage className="h-7 w-7" />}
        </span>
        <span className="text-base font-semibold text-slate-200">
          {full ? `Page limit reached (${maxPages})` : "Drop document photos here"}
        </span>
        <span className="text-sm text-slate-500">
          or <span className="text-accent-400 underline underline-offset-2">browse files</span> · JPEG / PNG /
          WebP / BMP / TIFF · up to 25 MB each
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED.join(",")}
        multiple
        className="hidden"
        disabled={disabled}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length > 0) onFiles(files);
          e.target.value = ""; // allow re-selecting the same file
        }}
      />
    </motion.div>
  );
}
