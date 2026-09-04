"use client";

/** Interactive crop & de-skew adjuster.
 *
 * Shows the uploaded photo with the detected quad overlaid.  The four
 * corner handles are draggable (pointer events, touch-friendly); the quad
 * is drawn with an SVG overlay in normalized coordinates, so any display
 * size maps 1:1 to the engine's coordinate space.
 */

import { useCallback, useRef, useState } from "react";
import { Crop, Maximize2, ScanSearch } from "lucide-react";
import type { Point } from "@/lib/types";
import { clamp } from "@/lib/format";

const CURSORS = ["nwse-resize", "nesw-resize", "nwse-resize", "nesw-resize"];
const LABELS = ["TL", "TR", "BR", "BL"];

const FULL_IMAGE: Point[] = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 1, y: 1 },
  { x: 0, y: 1 },
];

export default function CropAdjuster({
  src,
  corners,
  autoCorners,
  method,
  confidence,
  fileName,
  onChange,
  disabled,
}: {
  src: string;
  corners: Point[];
  autoCorners: Point[] | null;
  method?: string;
  confidence?: number;
  fileName?: string;
  onChange: (corners: Point[]) => void;
  disabled?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [aspect, setAspect] = useState(1.4); // updated on image load

  const updateCorner = useCallback(
    (index: number, clientX: number, clientY: number) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect || rect.width === 0) return;
      const next = corners.map((c, i) =>
        i === index
          ? { x: clamp((clientX - rect.left) / rect.width, 0, 1), y: clamp((clientY - rect.top) / rect.height, 0, 1) }
          : c
      );
      onChange(next);
    },
    [corners, onChange]
  );

  const isAuto =
    autoCorners !== null &&
    corners.length === 4 &&
    corners.every((c, i) => Math.abs(c.x - autoCorners[i].x) < 1e-4 && Math.abs(c.y - autoCorners[i].y) < 1e-4);

  const polygon = corners.map((c) => `${c.x},${c.y}`).join(" ");

  return (
    <div className="card p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-200">
          <Crop className="h-4 w-4 text-accent-400" />
          Crop &amp; de-skew
        </span>
        {method ? (
          <span className={`chip ${isAuto && method !== "fallback" ? "border-emerald-500/40 text-emerald-300" : ""}`}>
            <ScanSearch className="h-3 w-3" />
            {method === "fallback" ? "Auto-crop fallback (5% inset)" : `Auto-detected · ${method} · ${Math.round((confidence ?? 0) * 100)}%`}
          </span>
        ) : null}
        {fileName ? <span className="chip max-w-[16rem] truncate">{fileName}</span> : null}

        <div className="ml-auto flex gap-2">
          <button
            type="button"
            className="btn-ghost !px-3 !py-1.5 !text-xs"
            disabled={disabled || !autoCorners}
            onClick={() => autoCorners && onChange(autoCorners)}
          >
            Reset to auto
          </button>
          <button
            type="button"
            className="btn-ghost !px-3 !py-1.5 !text-xs"
            disabled={disabled}
            onClick={() => onChange(FULL_IMAGE)}
          >
            <Maximize2 className="h-3.5 w-3.5" />
            Full image
          </button>
        </div>
      </div>

      <div
        className="relative mx-auto w-full select-none overflow-hidden rounded-xl border border-surface-700 bg-surface-950"
        style={{ aspectRatio: String(aspect) }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt="Uploaded document preview"
          className="pointer-events-none absolute inset-0 h-full w-full object-fill"
          onLoad={(e) => {
            const img = e.currentTarget;
            if (img.naturalWidth > 0) setAspect(img.naturalWidth / img.naturalHeight);
          }}
          draggable={false}
        />

        <svg
          viewBox="0 0 1 1"
          preserveAspectRatio="none"
          className="pointer-events-none absolute inset-0 h-full w-full"
          aria-hidden
        >
          <polygon
            points={polygon}
            fill="rgba(99,102,241,0.14)"
            stroke="#818cf8"
            strokeWidth={0.004}
            vectorEffect="non-scaling-stroke"
          />
          {corners.map((c, i) => {
            const n = corners[(i + 1) % 4];
            return (
              <line
                key={i}
                x1={c.x}
                y1={c.y}
                x2={n.x}
                y2={n.y}
                stroke="#22d3ee"
                strokeWidth={0.003}
                strokeDasharray="0.012 0.01"
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
        </svg>

        {corners.map((corner, index) => (
          <button
            key={index}
            type="button"
            aria-label={`Corner ${LABELS[index]}`}
            disabled={disabled}
            onPointerDown={(e) => {
              e.preventDefault();
              e.currentTarget.setPointerCapture(e.pointerId);
              setDragIndex(index);
            }}
            onPointerMove={(e) => {
              if (dragIndex === index) updateCorner(index, e.clientX, e.clientY);
            }}
            onPointerUp={(e) => {
              e.currentTarget.releasePointerCapture(e.pointerId);
              setDragIndex(null);
            }}
            onPointerCancel={() => setDragIndex(null)}
            className={`absolute -ml-3 -mt-3 flex h-6 w-6 items-center justify-center rounded-full border-2 text-[9px] font-bold transition-[transform,border-color] ${
              dragIndex === index
                ? "scale-125 border-cyanx bg-cyanx/20 text-white"
                : "border-accent-400 bg-surface-900/90 text-accent-300 hover:scale-110"
            } ${disabled ? "cursor-default opacity-60" : "cursor-grab active:cursor-grabbing"}`}
            style={{
              left: `${corner.x * 100}%`,
              top: `${corner.y * 100}%`,
              cursor: disabled ? undefined : CURSORS[index],
              touchAction: "none",
            }}
          >
            {LABELS[index]}
          </button>
        ))}
      </div>

      <p className="mt-3 text-center text-xs text-slate-500">
        {isAuto
          ? "Corners are auto-detected — drag them if the detection missed the page edges."
          : "Manual crop active — the perspective warp follows your corners."}
      </p>
    </div>
  );
}
