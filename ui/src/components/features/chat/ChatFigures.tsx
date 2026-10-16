"use client";

import { useState } from "react";
import { ImageIcon } from "lucide-react";
import { ImagePreviewDialog } from "@/components/ui/ImagePreviewDialog";
import type { TraceStep } from "@/types/copilotChat";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "/api";

/** URL the API serves a calibration figure from, by its stored path. */
export function figureUrl(path: string): string {
  return `${BASE_URL}/executions/figure?path=${encodeURIComponent(path)}`;
}

/** File name without extension, e.g. "CheckRabi_0" from a figure path. */
export function figureLabel(path: string): string {
  const name = path.split("/").pop() ?? path;
  return name.replace(/\.[a-z0-9]+$/i, "");
}

/** Every figure the tools of a turn fetched, in order, without repeats. */
export function figuresInSteps(steps: TraceStep[]): string[] {
  const out: string[] = [];
  for (const step of steps) {
    if (step.kind !== "tool") continue;
    for (const path of step.figures ?? []) if (!out.includes(path)) out.push(path);
  }
  return out;
}

/**
 * Thumbnails of calibration figures, each opening the full image.
 *
 * `compact` is the row under a tool step; the default is the strip above an
 * answer that shows what the assistant looked at.
 */
export function FigureStrip({
  paths,
  compact = false,
  className = "",
}: {
  paths: string[];
  compact?: boolean;
  className?: string;
}) {
  const [preview, setPreview] = useState<string | null>(null);
  if (paths.length === 0) return null;
  const height = compact ? "h-14" : "h-20";

  return (
    <div className={className} data-testid="figure-strip">
      {!compact && (
        <div className="mb-1.5 flex items-center gap-1.5 text-xs text-base-content/50">
          <ImageIcon className="w-3.5 h-3.5" />
          <span>
            {paths.length} figure{paths.length === 1 ? "" : "s"}
          </span>
        </div>
      )}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {paths.map((path) => (
          <button
            key={path}
            type="button"
            onClick={() => setPreview(figureUrl(path))}
            title={figureLabel(path)}
            className="shrink-0 overflow-hidden rounded-lg border border-base-300 bg-base-200 transition-all hover:border-primary/50 hover:shadow-md"
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- API-served calibration figure */}
            <img
              src={figureUrl(path)}
              alt={figureLabel(path)}
              className={`${height} w-auto object-contain`}
              loading="lazy"
            />
          </button>
        ))}
      </div>
      <ImagePreviewDialog src={preview} onClose={() => setPreview(null)} />
    </div>
  );
}
