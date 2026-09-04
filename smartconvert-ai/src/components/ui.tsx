"use client";

/** Small shared UI atoms. */

import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return <Loader2 className={`animate-spin ${className}`} aria-hidden />;
}

export function StatCard({
  label,
  value,
  hint,
  accent = false,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-xl border border-surface-700/70 bg-surface-900/80 px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</div>
      <div
        className={`mt-1 font-mono text-lg font-semibold ${
          accent ? "text-cyanx" : "text-slate-100"
        }`}
      >
        {value}
      </div>
      {hint ? <div className="mt-0.5 text-xs text-slate-500">{hint}</div> : null}
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; className: string }> = {
    detecting: { label: "Detecting", className: "border-amber-500/40 text-amber-300" },
    ready: { label: "Ready", className: "border-cyan-500/40 text-cyan-300" },
    processing: { label: "Processing", className: "border-amber-500/40 text-amber-300" },
    processed: { label: "Done", className: "border-emerald-500/40 text-emerald-300" },
    error: { label: "Error", className: "border-red-500/40 text-red-300" },
  };
  const item = map[status] ?? { label: status, className: "border-surface-600 text-slate-400" };
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${item.className}`}>
      {status === "detecting" || status === "processing" ? (
        <Spinner className="mr-1 h-3 w-3" />
      ) : null}
      {item.label}
    </span>
  );
}
