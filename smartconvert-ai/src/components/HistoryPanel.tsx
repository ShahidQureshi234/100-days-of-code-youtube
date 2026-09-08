"use client";

/** Recent scan sessions from the database (auto-hidden without a DB). */

import { useEffect, useState } from "react";
import { History } from "lucide-react";
import { formatBytes, formatDate } from "@/lib/format";
import type { HistorySession } from "@/lib/types";

export default function HistoryPanel({ refreshKey }: { refreshKey: number }) {
  const [sessions, setSessions] = useState<HistorySession[] | null>(null);
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/history")
      .then((r) => r.json())
      .then((data: { ok: boolean; dbEnabled?: boolean; sessions?: HistorySession[] }) => {
        if (cancelled) return;
        setEnabled(data.dbEnabled !== false);
        setSessions(data.sessions ?? []);
      })
      .catch(() => !cancelled && setSessions([]));
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (!enabled) return null;

  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
        <History className="h-4 w-4 text-accent-400" />
        Scan history
      </div>
      {!sessions || sessions.length === 0 ? (
        <p className="text-xs text-slate-500">
          {sessions ? "No sessions recorded yet — your scans will appear here." : "Loading…"}
        </p>
      ) : (
        <ul className="divide-y divide-surface-700/60">
          {sessions.slice(0, 8).map((session) => (
            <li key={session.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2.5 text-xs">
              <span className="font-mono text-slate-400">{formatDate(session.createdAt)}</span>
              <span className="text-slate-300">
                {session.pageCount} page{session.pageCount === 1 ? "" : "s"}
              </span>
              {session.exportCount > 0 ? (
                <span className="text-cyanx">
                  {session.exportCount} export{session.exportCount === 1 ? "" : "s"} ·{" "}
                  {formatBytes(session.totalPdfBytes)}
                </span>
              ) : (
                <span className="text-slate-600">no exports</span>
              )}
              <span className="ml-auto max-w-[40%] truncate text-slate-500">
                {session.pages[0]?.originalName ?? ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
