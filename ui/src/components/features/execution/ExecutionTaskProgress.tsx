"use client";

import { useEffect, useMemo, useState } from "react";
import { LoaderCircle } from "lucide-react";

type TaskProgress = {
  current: number;
  total: number | null;
  description: string;
  etaSeconds: number | null;
  overallEtaSeconds: number | null;
  updatedAt: string;
  phase: number;
  hasMultiplePhases: boolean;
  phaseTotalMin: number | null;
  phaseTotalMax: number | null;
};

type ExecutionTaskProgressProps = {
  status?: string | null;
  note?: Record<string, unknown> | null;
};

function readProgress(note?: Record<string, unknown> | null): TaskProgress | null {
  const raw = note?.progress;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;

  const value = raw as Record<string, unknown>;
  if (typeof value.current !== "number" || !Number.isFinite(value.current)) return null;
  if (value.total !== null && (typeof value.total !== "number" || !Number.isFinite(value.total)))
    return null;
  if (typeof value.updated_at !== "string") return null;

  return {
    current: value.current,
    total: value.total as number | null,
    description: typeof value.description === "string" ? value.description : "",
    etaSeconds:
      typeof value.eta_seconds === "number" && Number.isFinite(value.eta_seconds)
        ? value.eta_seconds
        : null,
    overallEtaSeconds:
      typeof value.overall_eta_seconds === "number" && Number.isFinite(value.overall_eta_seconds)
        ? value.overall_eta_seconds
        : null,
    updatedAt: value.updated_at,
    phase: typeof value.phase === "number" && value.phase >= 1 ? value.phase : 1,
    hasMultiplePhases: value.has_multiple_phases === true,
    phaseTotalMin:
      typeof value.phase_total_min === "number" && value.phase_total_min >= 1
        ? value.phase_total_min
        : null,
    phaseTotalMax:
      typeof value.phase_total_max === "number" && value.phase_total_max >= 1
        ? value.phase_total_max
        : null,
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
    if (
      status !== "running" ||
      (progress?.etaSeconds == null && progress?.overallEtaSeconds == null)
    )
      return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [progress?.etaSeconds, progress?.overallEtaSeconds, status]);

  if (!["running", "scheduled", "pending"].includes(status ?? "")) return null;

  if (status !== "running" || progress === null) {
    return (
      <div
        className="mt-3 flex items-center gap-3 rounded-lg bg-base-200/60 p-3"
        role="status"
        aria-label="Task progress"
      >
        <LoaderCircle
          className="h-4 w-4 shrink-0 animate-spin text-primary motion-reduce:animate-none"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <p className="text-sm font-medium">
            {status === "running" ? "Preparing measurement" : "Waiting to start"}
          </p>
          <p className="text-xs text-base-content/60">
            Measurement progress will appear when available.
          </p>
        </div>
      </div>
    );
  }

  const percentage =
    progress.total && progress.total > 0
      ? Math.min(Math.max((progress.current / progress.total) * 100, 0), 100)
      : null;
  const updatedAt = Date.parse(progress.updatedAt);
  const ageSeconds = Number.isFinite(updatedAt) ? Math.max((now - updatedAt) / 1000, 0) : 0;
  const hasExactPhaseTotal =
    progress.phaseTotalMin !== null && progress.phaseTotalMin === progress.phaseTotalMax;
  const etaSeconds = hasExactPhaseTotal ? progress.overallEtaSeconds : progress.etaSeconds;
  const remainingSeconds = etaSeconds == null ? null : Math.max(etaSeconds - ageSeconds, 0);
  const completedSweeps = Math.min(
    progress.phase - 1 + (percentage === 100 ? 1 : 0),
    progress.phaseTotalMax ?? progress.phase,
  );
  const overallPercentage =
    percentage !== null && hasExactPhaseTotal && progress.phaseTotalMax !== null
      ? Math.min(
          Math.max(((progress.phase - 1 + percentage / 100) / progress.phaseTotalMax) * 100, 0),
          100,
        )
      : null;
  const phaseCount =
    progress.phaseTotalMin === null || progress.phaseTotalMax === null
      ? `${progress.phase}`
      : hasExactPhaseTotal
        ? `${progress.phase} / ${progress.phaseTotalMax}`
        : `${progress.phase} / ${progress.phaseTotalMin}–${progress.phaseTotalMax}`;

  const displayedPercentage = overallPercentage ?? percentage;
  const progressLabel = hasExactPhaseTotal
    ? "All sweeps"
    : progress.hasMultiplePhases
      ? "Current sweep"
      : "Measurement progress";
  const estimateLabel = hasExactPhaseTotal
    ? "All sweeps"
    : progress.hasMultiplePhases
      ? "This sweep"
      : "This measurement";

  return (
    <div
      className="mt-3 min-w-0 space-y-3 rounded-lg bg-base-200/60 p-3"
      aria-label="Task progress"
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium">{progressLabel}</span>
        {displayedPercentage !== null && (
          <span className="shrink-0 text-lg font-semibold tabular-nums text-primary">
            {displayedPercentage < 100 ? Math.min(Math.round(displayedPercentage), 99) : 100}%
          </span>
        )}
      </div>
      {displayedPercentage !== null ? (
        <progress
          className="progress progress-primary block h-2 w-full"
          value={displayedPercentage}
          max={100}
          aria-label={progressLabel}
        />
      ) : (
        <div className="flex items-center gap-2 text-xs text-base-content/60" role="status">
          <LoaderCircle
            className="h-3.5 w-3.5 animate-spin text-primary motion-reduce:animate-none"
            aria-hidden="true"
          />
          Measuring · total count unavailable
        </div>
      )}
      <div className="space-y-1.5 text-xs">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <span className="min-w-0 break-words text-base-content/80">
            {progress.description || "Measurement in progress"}
          </span>
          <span className="shrink-0 tabular-nums text-base-content/60">
            {hasExactPhaseTotal
              ? `${completedSweeps} / ${progress.phaseTotalMax} sweeps completed`
              : `${progress.hasMultiplePhases ? "Current sweep · " : ""}${
                  progress.total != null && progress.total > 0
                    ? `${progress.current} / ${progress.total} points`
                    : `${progress.current} points measured`
                }`}
          </span>
        </div>
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-base-content/60">
          {progress.hasMultiplePhases && !hasExactPhaseTotal && (
            <span className="tabular-nums">Sweep {phaseCount}</span>
          )}
          <span>
            {hasExactPhaseTotal && completedSweeps === progress.phaseTotalMax
              ? "Finishing measurement…"
              : remainingSeconds == null
                ? hasExactPhaseTotal
                  ? "Estimating remaining time for all sweeps…"
                  : "Estimating remaining time…"
                : remainingSeconds <= 0
                  ? "Updating time estimate…"
                  : `${estimateLabel} · ~${formatEta(remainingSeconds)} remaining`}
          </span>
        </div>
      </div>
    </div>
  );
}
