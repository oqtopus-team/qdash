"use client";

import dynamic from "next/dynamic";
import type { PlotMouseEvent } from "plotly.js";

import { TaskFigure } from "@/components/charts/TaskFigure";

const PlotlyRenderer = dynamic(
  () => import("@/components/charts/PlotlyRenderer").then((mod) => mod.PlotlyRenderer),
  { ssr: false },
);

export interface InteractiveFigureEntry {
  label: string;
  jsonPath?: string | null;
  staticPath?: string | null;
}

interface InteractiveFigureContentProps {
  figures: InteractiveFigureEntry[];
  qid: string;
  onPlotClick?: (event: PlotMouseEvent) => void;
}

export function InteractiveFigureContent({
  figures,
  qid,
  onPlotClick,
}: InteractiveFigureContentProps) {
  const visibleFigures = figures.filter((figure) => figure.jsonPath || figure.staticPath);
  if (visibleFigures.length === 0) return null;

  return (
    <div className="max-w-full overflow-x-auto pb-2">
      <div className="flex w-max gap-4">
        {visibleFigures.map((figure, index) => (
          <section
            key={`${figure.jsonPath ?? figure.staticPath}-${index}`}
            className="min-w-[min(88vw,760px)] max-w-[88vw]"
          >
            <div className="mb-2 text-sm font-semibold text-base-content/70">{figure.label}</div>
            <div className="h-fit max-h-[55vh] overflow-auto rounded-lg bg-white p-3 shadow">
              {figure.jsonPath ? (
                <PlotlyRenderer
                  fullPath={`/api/executions/figure?path=${encodeURIComponent(figure.jsonPath)}`}
                  onClick={onPlotClick}
                />
              ) : (
                <TaskFigure
                  path={figure.staticPath ?? undefined}
                  qid={qid}
                  className="h-auto max-h-[50vh] w-auto max-w-none object-contain"
                  hideExpandButton
                />
              )}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
