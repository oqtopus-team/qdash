"use client";

import { useEffect, useMemo, useState } from "react";

type TaskProgress = {
  current: number;
  total: number | null;
  description: string;
  etaSeconds: number | null;
  updatedAt: string;
};

type ExecutionTaskProgressProps = {
  status?: string | null;
  note?: Record<string, unknown> | null;
};

function readProgress(note?: Record<string, unknown> | null): TaskProgress | null {
  const raw = note?.progress;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;

  const value = raw as Record<string, unknown>;
  if (typeof value.current !== "number") return null;
  if (value.total !== null && typeof value.total !== "number") return null;
  if (typeof value.updated_at !== "string") return null;

  return {
    current: value.current,
    total: value.total as number | null,
    description: typeof value.description === "string" ? value.description : "",
    etaSeconds: typeof value.eta_seconds === "number" ? value.eta_seconds : null,
    updatedAt: value.updated_at,
  };
}

function formatEta(seconds: number): string {
  const rounded = Math.max(Math.ceil(seconds), 0);
  if (rounded < 60) return `${rounded}s`;
  const minutes = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  return remainder === 0 ? `${minutes}m` : `${minutes}m ${remainder}s`;
}

export function ExecutionTaskProgress({ status, note }: ExecutionTaskProgressProps) {
  const progress = useMemo(() => readProgress(note), [note]);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (status !== "running" || progress?.etaSeconds == null) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [progress?.etaSeconds, status]);

  if (status !== "running" || progress === null) return null;

  const percentage =
    progress.total && progress.total > 0
      ? Math.min(Math.max((progress.current / progress.total) * 100, 0), 100)
      : null;
  const ageSeconds = Math.max((now - Date.parse(progress.updatedAt)) / 1000, 0);
  const remainingSeconds =
    progress.etaSeconds == null ? null : Math.max(progress.etaSeconds - ageSeconds, 0);

  return (
    <div className="mt-3 space-y-1.5" aria-label="Task progress">
      <div className="flex items-center justify-between gap-3 text-xs text-base-content/70">
        <span className="truncate">{progress.description || "Measurement in progress"}</span>
        <span className="shrink-0 tabular-nums">
          {progress.total == null ? progress.current : `${progress.current} / ${progress.total}`}
        </span>
      </div>
      {percentage === null ? (
        <progress className="progress progress-info w-full" />
      ) : (
        <progress
          className="progress progress-info w-full"
          value={percentage}
          max={100}
          aria-label={`${Math.round(percentage)}% complete`}
        />
      )}
      <p className="text-right text-xs text-base-content/60 tabular-nums">
        {remainingSeconds == null
          ? "Calculating phase estimate…"
          : `Estimated ${formatEta(remainingSeconds)} remaining in this phase`}
      </p>
    </div>
  );
}
