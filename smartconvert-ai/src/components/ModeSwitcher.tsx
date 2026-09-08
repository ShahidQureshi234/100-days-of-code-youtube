"use client";

/** Mode switcher: B&W Xerox vs Smart Color. */

import { motion } from "framer-motion";
import { Palette, Scan } from "lucide-react";
import type { ScanMode } from "@/lib/types";

const MODES: {
  id: ScanMode;
  title: string;
  subtitle: string;
  sizeHint: string;
  icon: typeof Scan;
}[] = [
  {
    id: "bw",
    title: "B&W Xerox",
    subtitle: "Pure black text · zero shadow · CCITT G4",
    sizeHint: "~20–80 KB / page",
    icon: Scan,
  },
  {
    id: "color",
    title: "Smart Color",
    subtitle: "Colors preserved · background whitened · MRC",
    sizeHint: "~150–350 KB / page",
    icon: Palette,
  },
];

export default function ModeSwitcher({
  mode,
  onChange,
  disabled,
}: {
  mode: ScanMode;
  onChange: (mode: ScanMode) => void;
  disabled?: boolean;
}) {
  return (
    <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-label="Scan mode">
      {MODES.map((item) => {
        const active = mode === item.id;
        const Icon = item.icon;
        return (
          <button
            key={item.id}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={() => onChange(item.id)}
            className={`relative overflow-hidden rounded-2xl border p-4 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 disabled:cursor-not-allowed disabled:opacity-50 ${
              active
                ? "border-accent-500/70 bg-gradient-to-br from-accent-500/15 to-cyan-500/5"
                : "border-surface-700 bg-surface-900/60 hover:border-surface-600"
            }`}
          >
            {active ? (
              <motion.span
                layoutId="mode-glow"
                className="pointer-events-none absolute inset-0 rounded-2xl shadow-glow"
                transition={{ type: "spring", stiffness: 350, damping: 30 }}
              />
            ) : null}
            <div className="flex items-start justify-between">
              <span
                className={`flex h-10 w-10 items-center justify-center rounded-xl ${
                  active ? "bg-accent-500/25 text-accent-300" : "bg-surface-800 text-slate-400"
                }`}
              >
                <Icon className="h-5 w-5" />
              </span>
              <span
                className={`rounded-full px-2 py-0.5 font-mono text-[11px] ${
                  active ? "bg-cyan-500/15 text-cyan-300" : "bg-surface-800 text-slate-500"
                }`}
              >
                {item.sizeHint}
              </span>
            </div>
            <div className="mt-3 text-sm font-semibold text-slate-100">{item.title}</div>
            <div className="mt-0.5 text-xs leading-relaxed text-slate-500">{item.subtitle}</div>
          </button>
        );
      })}
    </div>
  );
}
