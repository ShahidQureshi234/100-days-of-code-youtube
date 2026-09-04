"use client";

/**
 * ScanWorkbench -- the app's orchestrator.
 *
 * Page lifecycle:  upload -> detect (auto corners) -> [user adjusts crop]
 *                  -> process (warp + filter) -> export (single PDF).
 *
 * All heavy lifting happens in the Python engine behind the API routes;
 * this component owns state, sequencing and error surfaces.
 */

import { useCallback, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileText,
  Play,
  Trash2,
  X,
} from "lucide-react";
import UploadZone, { clientValidate } from "./UploadZone";
import CropAdjuster from "./CropAdjuster";
import ModeSwitcher from "./ModeSwitcher";
import SettingsPanel, { DEFAULT_DPI, DEFAULT_SETTINGS } from "./SettingsPanel";
import ResultViewer from "./ResultViewer";
import HistoryPanel from "./HistoryPanel";
import { StatusBadge, Spinner } from "./ui";
import { formatBytes } from "@/lib/format";
import type {
  DetectResponse,
  EngineSettings,
  Point,
  ProcessResponse,
  ProcessSuccess,
  ScanMode,
} from "@/lib/types";

type PageStatus = "detecting" | "ready" | "processing" | "processed" | "error";

interface PageState {
  key: string;
  pageId: string | null;
  fileName: string;
  fileSize: number;
  status: PageStatus;
  error?: string;
  width?: number;
  height?: number;
  detectedCorners: Point[] | null;
  corners: Point[];
  method?: string;
  confidence?: number;
  urls?: { original: string; previewOriginal: string; previewDetect: string };
  result: ProcessSuccess | null;
}

const MAX_PAGES = 20;

function newPage(fileName: string, fileSize: number): PageState {
  return {
    key: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    pageId: null,
    fileName,
    fileSize,
    status: "detecting",
    detectedCorners: null,
    corners: [],
    result: null,
  };
}

export default function ScanWorkbench() {
  const [pages, setPages] = useState<PageState[]>([]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [mode, setMode] = useState<ScanMode>("bw");
  const [settings, setSettings] = useState<EngineSettings>(DEFAULT_SETTINGS);
  const [dpi, setDpi] = useState(DEFAULT_DPI);
  const [colorCodec, setColorCodec] = useState<"jpeg" | "jp2">("jpeg");
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportDone, setExportDone] = useState<{ bytes: number; url: string; filename: string } | null>(null);
  const [toasts, setToasts] = useState<{ id: number; kind: "error" | "info"; text: string }[]>([]);
  const [historyKey, setHistoryKey] = useState(0);
  const sessionIdRef = useRef<string | null>(null);
  const [filename, setFilename] = useState("smartconvert-scan.pdf");

  const pushToast = useCallback((kind: "error" | "info", text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);

  const patchPage = useCallback((key: string, patch: Partial<PageState>) => {
    setPages((prev) => prev.map((p) => (p.key === key ? { ...p, ...patch } : p)));
  }, []);

  // ------------------------------------------------------------------ //
  // Upload + auto-detect
  // ------------------------------------------------------------------ //
  const handleFiles = useCallback(
    async (files: File[]) => {
      if (busy) return;
      setBusy(true);
      try {
        for (const file of files) {
          const invalid = clientValidate(file);
          if (invalid) {
            pushToast("error", invalid);
            continue;
          }
          const state = newPage(file.name, file.size);
          setPages((prev) => {
            const next = [...prev, state];
            return next.length > MAX_PAGES ? next.slice(0, MAX_PAGES) : next;
          });
          setActiveKey((k) => k ?? state.key);

          try {
            const form = new FormData();
            form.append("file", file);
            const headers: Record<string, string> = {};
            if (sessionIdRef.current) headers["X-Session-Id"] = sessionIdRef.current;

            const res = await fetch("/api/detect", { method: "POST", body: form, headers });
            const data = (await res.json()) as DetectResponse;
            if (!data.ok) throw new Error(data.error);

            sessionIdRef.current = data.sessionId;
            patchPage(state.key, {
              pageId: data.pageId,
              status: "ready",
              width: data.width,
              height: data.height,
              detectedCorners: data.corners,
              corners: data.corners,
              method: data.method,
              confidence: data.confidence,
              urls: data.urls,
            });
            if (data.method === "fallback") {
              pushToast("info", `No document edges found in "${file.name}" — using 5% inset auto-crop.`);
            }
          } catch (err) {
            patchPage(state.key, {
              status: "error",
              error: err instanceof Error ? err.message : "detection failed",
            });
            pushToast("error", `"${file.name}": ${err instanceof Error ? err.message : "detection failed"}`);
          }
        }
      } finally {
        setBusy(false);
      }
    },
    [busy, patchPage, pushToast]
  );

  // ------------------------------------------------------------------ //
  // Process (warp + filter)
  // ------------------------------------------------------------------ //
  const processAll = useCallback(async () => {
    const targets = pages.filter((p) => p.pageId && p.status !== "error" && p.status !== "detecting");
    if (targets.length === 0) return;
    setBusy(true);
    setExportDone(null);
    try {
      for (const page of targets) {
        patchPage(page.key, { status: "processing" });
        try {
          const res = await fetch("/api/process", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              pageId: page.pageId,
              corners: page.corners,
              mode,
              settings,
              dpi,
              colorCodec,
              sessionId: sessionIdRef.current ?? undefined,
              originalName: page.fileName,
            }),
          });
          const data = (await res.json()) as ProcessResponse;
          if (!data.ok) throw new Error(data.error);
          patchPage(page.key, { status: "processed", result: data });
        } catch (err) {
          patchPage(page.key, { status: "error", error: err instanceof Error ? err.message : "processing failed" });
          pushToast("error", `"${page.fileName}": ${err instanceof Error ? err.message : "processing failed"}`);
        }
      }
      setHistoryKey((k) => k + 1);
    } finally {
      setBusy(false);
    }
  }, [colorCodec, dpi, mode, pages, patchPage, pushToast, settings]);

  // ------------------------------------------------------------------ //
  // Export
  // ------------------------------------------------------------------ //
  const processedPages = useMemo(
    () => pages.filter((p) => p.status === "processed" && p.result && p.result.mode === mode),
    [pages, mode]
  );
  const stalePages = pages.filter((p) => p.status === "processed" && p.result && p.result.mode !== mode);

  const exportPdf = useCallback(async () => {
    if (processedPages.length === 0 || exporting) return;
    setExporting(true);
    try {
      const res = await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pageIds: processedPages.map((p) => p.pageId),
          mode,
          filename,
          dpi,
          colorCodec,
          useMrc: true,
          sessionId: sessionIdRef.current ?? undefined,
        }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => null)) as { error?: string } | null;
        throw new Error(data?.error || `export failed (${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const safeName = filename.endsWith(".pdf") ? filename : `${filename}.pdf`;
      const link = document.createElement("a");
      link.href = url;
      link.download = safeName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setExportDone({ bytes: blob.size, url, filename: safeName });
      setHistoryKey((k) => k + 1);
      pushToast("info", `PDF exported — ${formatBytes(blob.size)} (${processedPages.length} page${processedPages.length === 1 ? "" : "s"}).`);
    } catch (err) {
      pushToast("error", err instanceof Error ? err.message : "export failed");
    } finally {
      setExporting(false);
    }
  }, [colorCodec, dpi, exportDone, filename, mode, processedPages, exporting, pushToast]);

  // ------------------------------------------------------------------ //
  // Misc actions
  // ------------------------------------------------------------------ //
  const removePage = useCallback(
    (key: string) => {
      setPages((prev) => {
        const next = prev.filter((p) => p.key !== key);
        if (activeKey === key) setActiveKey(next[0]?.key ?? null);
        return next;
      });
    },
    [activeKey]
  );

  const activePage = pages.find((p) => p.key === activeKey) ?? pages[0] ?? null;
  const allDone = pages.length > 0 && processedPages.length === pages.filter((p) => p.status !== "error").length;

  const totals = useMemo(() => {
    let original = 0;
    let processed = 0;
    for (const page of processedPages) {
      original += page.result?.stats.originalBytes ?? 0;
      processed += page.result?.stats.processedBytes ?? 0;
    }
    return { original, processed };
  }, [processedPages]);

  return (
    <div className="mx-auto w-full max-w-7xl px-4 pb-16 sm:px-6">
      {/* Toasts */}
      <div className="pointer-events-none fixed inset-x-0 top-4 z-50 flex flex-col items-center gap-2 px-4">
        <AnimatePresence>
          {toasts.map((toast) => (
            <motion.div
              key={toast.id}
              initial={{ opacity: 0, y: -12, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8 }}
              className={`pointer-events-auto flex max-w-lg items-start gap-2 rounded-xl border px-4 py-2.5 text-sm shadow-card backdrop-blur ${
                toast.kind === "error"
                  ? "border-red-500/40 bg-red-950/80 text-red-200"
                  : "border-cyan-500/40 bg-surface-900/90 text-cyan-100"
              }`}
            >
              {toast.kind === "error" ? (
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              ) : (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              )}
              <span>{toast.text}</span>
              <button
                type="button"
                className="ml-2 opacity-60 hover:opacity-100"
                onClick={() => setToasts((t) => t.filter((x) => x.id !== toast.id))}
                aria-label="Dismiss"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Step 1: upload */}
      <section className="mt-6" aria-label="Upload">
        <UploadZone
          onFiles={handleFiles}
          disabled={busy || exporting}
          maxPages={MAX_PAGES}
          pageCount={pages.length}
        />
      </section>

      {pages.length === 0 ? null : (
        <>
          {/* Pages strip */}
          <section className="mt-6" aria-label="Pages">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-300">
                Pages <span className="text-slate-500">({pages.length})</span>
              </h2>
              <button
                type="button"
                className="btn-ghost !px-3 !py-1.5 !text-xs"
                onClick={() => {
                  setPages([]);
                  setActiveKey(null);
                  setExportDone(null);
                }}
                disabled={busy || exporting}
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear all
              </button>
            </div>
            <div className="flex gap-3 overflow-x-auto pb-2">
              <AnimatePresence initial={false}>
                {pages.map((page, index) => (
                  <motion.button
                    key={page.key}
                    layout
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.9 }}
                    type="button"
                    onClick={() => setActiveKey(page.key)}
                    className={`group relative w-36 shrink-0 overflow-hidden rounded-xl border text-left transition ${
                      page.key === activePage?.key
                        ? "border-accent-500 shadow-glow"
                        : "border-surface-700 hover:border-surface-600"
                    }`}
                  >
                    <div className="flex h-24 items-center justify-center bg-surface-950">
                      {page.urls ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={page.urls.previewDetect}
                          alt={page.fileName}
                          className="h-full w-full object-cover opacity-90"
                          draggable={false}
                        />
                      ) : (
                        <Spinner className="h-5 w-5 text-slate-500" />
                      )}
                    </div>
                    <div className="flex items-center justify-between gap-1 bg-surface-900/90 px-2 py-1.5">
                      <span className="truncate text-[11px] text-slate-400">
                        {index + 1}. {page.fileName}
                      </span>
                      <span
                        role="button"
                        tabIndex={0}
                        className="rounded p-0.5 text-slate-600 opacity-0 transition hover:text-red-400 group-hover:opacity-100"
                        onClick={(e) => {
                          e.stopPropagation();
                          removePage(page.key);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.stopPropagation();
                            removePage(page.key);
                          }
                        }}
                        aria-label={`Remove ${page.fileName}`}
                      >
                        <X className="h-3.5 w-3.5" />
                      </span>
                    </div>
                    <span className="absolute left-2 top-2">
                      <StatusBadge status={page.status} />
                    </span>
                  </motion.button>
                ))}
              </AnimatePresence>
            </div>
          </section>

          {/* Workbench grid */}
          <div className="mt-4 grid gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,4fr)]">
            <div className="flex flex-col gap-5">
              {activePage && activePage.urls && activePage.detectedCorners ? (
                <CropAdjuster
                  key={activePage.key}
                  src={activePage.urls.previewOriginal}
                  corners={activePage.corners}
                  autoCorners={activePage.detectedCorners}
                  method={activePage.method}
                  confidence={activePage.confidence}
                  fileName={activePage.fileName}
                  disabled={busy || exporting}
                  onChange={(corners) => patchPage(activePage.key, { corners })}
                />
              ) : (
                <div className="card flex min-h-[16rem] items-center justify-center p-6 text-sm text-slate-500">
                  {activePage?.status === "error"
                    ? `Upload failed: ${activePage.error}`
                    : "Waiting for detection…"}
                </div>
              )}

              <ModeSwitcher mode={mode} onChange={setMode} disabled={busy || exporting} />
              <SettingsPanel
                mode={mode}
                settings={settings}
                dpi={dpi}
                colorCodec={colorCodec}
                onChange={setSettings}
                onDpiChange={setDpi}
                onCodecChange={setColorCodec}
                disabled={busy || exporting}
              />

              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  className="btn-primary"
                  onClick={processAll}
                  disabled={busy || exporting || pages.every((p) => !p.pageId)}
                >
                  {busy ? <Spinner /> : <Play className="h-4 w-4" />}
                  {busy ? "Working…" : `Process ${pages.filter((p) => p.pageId).length} page${pages.filter((p) => p.pageId).length === 1 ? "" : "s"}`}
                </button>
                {stalePages.length > 0 ? (
                  <span className="text-xs text-amber-400">
                    {stalePages.length} page{stalePages.length === 1 ? "" : "s"} processed in the other mode —
                    reprocess to switch.
                  </span>
                ) : null}
              </div>
            </div>

            <div className="flex flex-col gap-5">
              <ResultViewer
                result={activePage?.result ?? null}
                beforeUrl={activePage?.urls?.previewOriginal}
                mode={mode}
              />

              {/* Export bar */}
              <div className="card p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
                  <FileText className="h-4 w-4 text-accent-400" />
                  Export PDF
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <input
                    type="text"
                    value={filename}
                    onChange={(e) => setFilename(e.target.value)}
                    className="min-w-0 flex-1 rounded-lg border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-accent-500 focus:outline-none"
                    placeholder="smartconvert-scan.pdf"
                    aria-label="Output filename"
                  />
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={exportPdf}
                    disabled={exporting || processedPages.length === 0}
                  >
                    {exporting ? <Spinner /> : <Download className="h-4 w-4" />}
                    {exporting
                      ? "Exporting…"
                      : `Export ${processedPages.length} page${processedPages.length === 1 ? "" : "s"}`}
                  </button>
                </div>

                {processedPages.length === 0 ? (
                  <p className="mt-3 text-xs text-slate-500">
                    Process pages first — the export assembles every processed page into one PDF.
                  </p>
                ) : (
                  <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                    <div className="rounded-lg bg-surface-800/70 px-2 py-2">
                      <div className="font-mono text-sm text-slate-200">{formatBytes(totals.original)}</div>
                      <div className="text-slate-500">original</div>
                    </div>
                    <div className="rounded-lg bg-surface-800/70 px-2 py-2">
                      <div className="font-mono text-sm text-cyanx">{formatBytes(totals.processed)}</div>
                      <div className="text-slate-500">estimated</div>
                    </div>
                    <div className="rounded-lg bg-surface-800/70 px-2 py-2">
                      <div className="font-mono text-sm text-emerald-400">
                        {totals.original > 0
                          ? `${Math.round(100 * (1 - totals.processed / totals.original))}%`
                          : "—"}
                      </div>
                      <div className="text-slate-500">lighter</div>
                    </div>
                  </div>
                )}

                {exportDone ? (
                  <a
                    href={exportDone.url}
                    download={exportDone.filename}
                    className="mt-3 flex items-center justify-between rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-200 transition hover:bg-emerald-500/20"
                  >
                    <span className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4" />
                      {exportDone.filename} · {formatBytes(exportDone.bytes)} ready
                    </span>
                    <Download className="h-4 w-4" />
                  </a>
                ) : null}

                {allDone && !exportDone ? (
                  <p className="mt-3 text-xs text-emerald-400">
                    All pages processed — ready to export.
                  </p>
                ) : null}
              </div>
            </div>
          </div>
        </>
      )}

      <div className="mt-6">
        <HistoryPanel refreshKey={historyKey} />
      </div>
    </div>
  );
}
