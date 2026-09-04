"use client";

/** Before/after preview with compression statistics. */

import { motion } from "framer-motion";
import { Eye, EyeOff, Sparkles } from "lucide-react";
import { useState } from "react";
import { StatCard } from "./ui";
import { formatBytes, formatMs } from "@/lib/format";
import type { ProcessSuccess } from "@/lib/types";

export default function ResultViewer({
  result,
  beforeUrl,
  mode,
}: {
  result: ProcessSuccess | null;
  beforeUrl?: string;
  mode: string;
}) {
  const [showAfter, setShowAfter] = useState(true);

  if (!result) {
    return (
      <div className="card flex h-full min-h-[18rem] flex-col items-center justify-center gap-3 p-6 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-surface-800 text-slate-500">
          <Sparkles className="h-6 w-6" />
        </span>
        <div className="text-sm font-semibold text-slate-300">No processed output yet</div>
        <p className="max-w-sm text-xs leading-relaxed text-slate-500">
          Adjust the crop corners, pick a mode, then hit <span className="text-accent-300">Process pages</span>.
          The scanner will de-skew, clean and compress every page.
        </p>
      </div>
    );
  }

  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-slate-200">Result</span>
        <div className="flex items-center gap-2">
          <span className="chip border-cyan-500/40 text-cyan-300">
            {mode === "bw" ? "B&W Xerox" : "Smart Color"} · {String(result.format)}
          </span>
          <button
            type="button"
            className="btn-ghost !px-3 !py-1.5 !text-xs"
            onClick={() => setShowAfter((v) => !v)}
          >
            {showAfter ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            {showAfter ? "Show before" : "Show after"}
          </button>
        </div>
      </div>

      <motion.div
        key={showAfter ? "after" : "before"}
        initial={{ opacity: 0, scale: 0.985 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.22 }}
        className="overflow-hidden rounded-xl border border-surface-700 bg-white"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={showAfter ? result.urls.preview : beforeUrl}
          alt={showAfter ? "Processed scan" : "Original photo"}
          className="max-h-[26rem] w-full bg-white object-contain"
          draggable={false}
        />
      </motion.div>

      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Original" value={formatBytes(result.stats.originalBytes)} />
        <StatCard label="After" value={formatBytes(result.stats.processedBytes)} hint={String(result.format)} />
        <StatCard label="Reduction" value={`${result.stats.reductionPct}%`} accent />
        <StatCard
          label="Output"
          value={`${result.outputWidth}×${result.outputHeight}`}
          hint={`engine ${formatMs(result.elapsedMs)}`}
        />
      </div>
    </div>
  );
}
