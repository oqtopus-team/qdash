"use client";

import dynamic from "next/dynamic";

const PlotlyRenderer = dynamic(
  () => import("@/app/components/PlotlyRenderer").then((mod) => mod.default),
  { ssr: false },
);

interface InteractiveFigureContentProps {
  figureJsonPath: string;
  figureIndex?: number;
  totalFigures?: number;
  onNavigatePrevious?: () => void;
  onNavigateNext?: () => void;
}

export function InteractiveFigureContent({
  figureJsonPath,
  figureIndex,
  totalFigures,
  onNavigatePrevious,
  onNavigateNext,
}: InteractiveFigureContentProps) {
  const showNavigation =
    totalFigures !== undefined &&
    totalFigures > 1 &&
    figureIndex !== undefined &&
    onNavigatePrevious &&
    onNavigateNext;

  return (
    <>
      <div className="w-fit max-w-full h-fit max-h-[78vh] bg-white rounded-xl p-4 shadow overflow-auto">
        <PlotlyRenderer
          fullPath={`${
            process.env.NEXT_PUBLIC_API_URL
          }/api/executions/figure?path=${encodeURIComponent(figureJsonPath)}`}
        />
      </div>
      {showNavigation && (
        <div className="mt-4 flex justify-center gap-2">
          <button
            className="btn btn-xs"
            onClick={onNavigatePrevious}
            disabled={figureIndex === 0}
          >
            ◀
          </button>
          <span className="text-sm">
            {figureIndex! + 1} / {totalFigures}
          </span>
          <button
            className="btn btn-xs"
            onClick={onNavigateNext}
            disabled={figureIndex === totalFigures! - 1}
          >
            ▶
          </button>
        </div>
      )}
    </>
  );
}
