"use client";

/** Advanced tuning sliders (mirrors the Python engine dataclasses). */

import { useState } from "react";
import { ChevronDown, RotateCcw, SlidersHorizontal } from "lucide-react";
import type { EngineSettings, ScanMode } from "@/lib/types";

export const DEFAULT_SETTINGS: EngineSettings = {
  bwC: 10,
  bwBlockSize: 15,
  bwUnsharpAlpha: 0.5,
  bwDespeckle: true,
  colorWhiteThreshold: 220,
  colorClaheClip: 2.0,
  colorQuality: 72,
};

export const DEFAULT_DPI = 300;

interface SliderProps {
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format?: (v: number) => string;
  onChange: (v: number) => void;
}

function Slider({ label, hint, value, min, max, step, format, onChange }: SliderProps) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-medium text-slate-300">{label}</span>
        <span className="font-mono text-xs text-cyanx">{format ? format(value) : value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2"
      />
      <div className="mt-1 text-[11px] leading-snug text-slate-500">{hint}</div>
    </label>
  );
}

export default function SettingsPanel({
  mode,
  settings,
  dpi,
  colorCodec,
  onChange,
  onDpiChange,
  onCodecChange,
  disabled,
}: {
  mode: ScanMode;
  settings: EngineSettings;
  dpi: number;
  colorCodec: "jpeg" | "jp2";
  onChange: (settings: EngineSettings) => void;
  onDpiChange: (dpi: number) => void;
  onCodecChange: (codec: "jpeg" | "jp2") => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-400"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-200">
          <SlidersHorizontal className="h-4 w-4 text-accent-400" />
          Advanced settings
        </span>
        <ChevronDown className={`h-4 w-4 text-slate-500 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open ? (
        <div className="border-t border-surface-700/60 px-4 py-4">
          {mode === "bw" ? (
            <div className="grid gap-5 sm:grid-cols-2">
              <Slider
                label="Threshold C"
                hint="Constant subtracted from the local mean — higher removes fainter noise."
                value={settings.bwC ?? DEFAULT_SETTINGS.bwC!}
                min={0}
                max={30}
                step={1}
                onChange={(v) => onChange({ ...settings, bwC: v })}
              />
              <Slider
                label="Block size"
                hint="Adaptive threshold neighborhood (odd). Larger tolerates uneven paper."
                value={settings.bwBlockSize ?? DEFAULT_SETTINGS.bwBlockSize!}
                min={11}
                max={31}
                step={2}
                onChange={(v) => onChange({ ...settings, bwBlockSize: v })}
              />
              <Slider
                label="Unsharp α"
                hint="Stroke-edge locking before binarization (spec: 0.5)."
                value={settings.bwUnsharpAlpha ?? DEFAULT_SETTINGS.bwUnsharpAlpha!}
                min={0}
                max={1}
                step={0.05}
                format={(v) => v.toFixed(2)}
                onChange={(v) => onChange({ ...settings, bwUnsharpAlpha: v })}
              />
              <label className="flex items-center gap-3 self-end pb-1 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={settings.bwDespeckle ?? true}
                  onChange={(e) => onChange({ ...settings, bwDespeckle: e.target.checked })}
                  className="h-4 w-4 rounded border-surface-600 bg-surface-800 accent-indigo-500"
                />
                Despeckle (remove dust)
              </label>
            </div>
          ) : (
            <div className="grid gap-5 sm:grid-cols-3">
              <Slider
                label="White threshold"
                hint="LAB lightness above this becomes pure white (spec: 220)."
                value={settings.colorWhiteThreshold ?? DEFAULT_SETTINGS.colorWhiteThreshold!}
                min={180}
                max={245}
                step={1}
                onChange={(v) => onChange({ ...settings, colorWhiteThreshold: v })}
              />
              <Slider
                label="CLAHE clip"
                hint="Contrast limit for photos/logos (spec: 2.0)."
                value={settings.colorClaheClip ?? DEFAULT_SETTINGS.colorClaheClip!}
                min={1}
                max={4}
                step={0.1}
                format={(v) => v.toFixed(1)}
                onChange={(v) => onChange({ ...settings, colorClaheClip: v })}
              />
              <Slider
                label="Quality"
                hint="Color layer quality (spec: 70–75)."
                value={settings.colorQuality ?? DEFAULT_SETTINGS.colorQuality!}
                min={65}
                max={85}
                step={1}
                onChange={(v) => onChange({ ...settings, colorQuality: v })}
              />
            </div>
          )}

          <div className="mt-5 flex flex-wrap items-end gap-4 border-t border-surface-700/60 pt-4">
            <label className="block">
              <span className="text-xs font-medium text-slate-300">Output DPI</span>
              <select
                value={dpi}
                disabled={disabled}
                onChange={(e) => onDpiChange(Number(e.target.value))}
                className="mt-1.5 block rounded-lg border border-surface-600 bg-surface-800 px-3 py-1.5 text-sm text-slate-200 focus:border-accent-500 focus:outline-none"
              >
                {[150, 200, 300, 400].map((d) => (
                  <option key={d} value={d}>
                    {d} DPI
                  </option>
                ))}
              </select>
            </label>

            {mode === "color" ? (
              <label className="block">
                <span className="text-xs font-medium text-slate-300">Color codec</span>
                <select
                  value={colorCodec}
                  disabled={disabled}
                  onChange={(e) => onCodecChange(e.target.value as "jpeg" | "jp2")}
                  className="mt-1.5 block rounded-lg border border-surface-600 bg-surface-800 px-3 py-1.5 text-sm text-slate-200 focus:border-accent-500 focus:outline-none"
                >
                  <option value="jpeg">JPEG (DCTDecode)</option>
                  <option value="jp2">JPEG 2000 (JPXDecode)</option>
                </select>
              </label>
            ) : null}

            <button
              type="button"
              className="btn-ghost ml-auto"
              disabled={disabled}
              onClick={() => {
                onChange(DEFAULT_SETTINGS);
                onDpiChange(DEFAULT_DPI);
                onCodecChange("jpeg");
              }}
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Reset defaults
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
