import { ScanLine, ShieldCheck, Zap } from "lucide-react";
import ScanWorkbench from "@/components/ScanWorkbench";

export default function HomePage() {
  return (
    <main className="min-h-screen">
      {/* Header */}
      <header className="border-b border-surface-700/60 bg-surface-950/70 backdrop-blur">
        <div className="mx-auto flex w-full max-w-7xl items-center gap-3 px-4 py-4 sm:px-6">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-accent-500 to-cyan-500 shadow-glow">
            <ScanLine className="h-5 w-5 text-white" />
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-bold tracking-tight text-white">
              SmartConvert<span className="text-accent-400">AI</span>
            </h1>
            <p className="truncate text-xs text-slate-500">
              Industrial Xerox-grade document scanning, in your browser
            </p>
          </div>
          <div className="ml-auto hidden items-center gap-4 text-xs text-slate-500 sm:flex">
            <span className="flex items-center gap-1.5">
              <Zap className="h-3.5 w-3.5 text-cyanx" />
              Canny + perspective de-skew
            </span>
            <span className="flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
              CCITT G4 · MRC PDF
            </span>
          </div>
        </div>
      </header>

      <ScanWorkbench />

      {/* Footer */}
      <footer className="border-t border-surface-700/60 py-6">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-2 px-4 text-xs text-slate-600 sm:px-6">
          <span>
            SmartConvertAI · Next.js + OpenCV engine · Mode A: 20–80 KB B&amp;W pages · Mode B: 150–350 KB color
            pages
          </span>
          <span className="font-mono">v1.0.0</span>
        </div>
      </footer>
    </main>
  );
}
