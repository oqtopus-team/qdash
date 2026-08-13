"use client";

import dynamic from "next/dynamic";
import { Maximize2, X } from "lucide-react";
import { Component, type ReactNode, useCallback, useState } from "react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";

const Plot = dynamic(() => import("@/components/charts/Plot"), { ssr: false });

interface ChatPlotlyChartProps {
  data: Record<string, unknown>[];
  layout: Record<string, unknown>;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

class ChartErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-lg border border-error/30 bg-error/5 p-3 text-xs text-error">
          Chart rendering failed. The data may be in an unsupported format.
        </div>
      );
    }
    return this.props.children;
  }
}

export function ChatPlotlyChart({ data, layout }: ChatPlotlyChartProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const openLightbox = useCallback(() => {
    setIsExpanded(true);
  }, []);

  const closeLightbox = useCallback(() => {
    setIsExpanded(false);
  }, []);

  const mergedLayout = {
    autosize: true,
    height: 300,
    margin: { l: 50, r: 20, t: 40, b: 40 },
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { size: 11 },
    ...layout,
  };

  const expandedLayout = {
    autosize: true,
    margin: { l: 60, r: 30, t: 50, b: 50 },
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { size: 13 },
    ...layout,
    height: undefined,
  };

  return (
    <>
      <ChartErrorBoundary>
        <div className="w-full my-2 rounded-lg border border-base-300 overflow-hidden">
          <div className="flex justify-end px-2 pt-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={openLightbox}
                  className="btn btn-xs btn-ghost btn-square"
                  aria-label="Expand chart"
                >
                  <Maximize2 className="w-4 h-4" aria-hidden="true" />
                </button>
              </TooltipTrigger>
              <TooltipContent>Expand chart</TooltipContent>
            </Tooltip>
          </div>
          <Plot
            data={data as Plotly.Data[]}
            layout={mergedLayout as Partial<Plotly.Layout>}
            config={{
              displayModeBar: "hover",
              responsive: true,
              displaylogo: false,
              modeBarButtonsToRemove: ["lasso2d", "select2d"],
            }}
            useResizeHandler
            style={{ width: "100%", height: "300px" }}
          />
        </div>
      </ChartErrorBoundary>

      <Dialog open={isExpanded} onOpenChange={setIsExpanded}>
        <DialogContent className="max-w-5xl h-[80vh] flex flex-col p-4 !overflow-hidden">
          <div className="flex justify-between items-center mb-2">
            <DialogTitle className="text-sm">
              {typeof layout.title === "string"
                ? layout.title
                : (((layout.title as Record<string, unknown>)?.text as string) ?? "Chart")}
            </DialogTitle>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={closeLightbox}
                  className="btn btn-sm btn-ghost btn-square"
                  aria-label="Close expanded chart"
                >
                  <X className="w-4 h-4" aria-hidden="true" />
                </button>
              </TooltipTrigger>
              <TooltipContent>Close</TooltipContent>
            </Tooltip>
          </div>
          <DialogDescription className="sr-only">Expanded interactive chart.</DialogDescription>
          <div className="flex-1 min-h-0">
            {isExpanded && (
              <ChartErrorBoundary>
                <Plot
                  data={data as Plotly.Data[]}
                  layout={expandedLayout as Partial<Plotly.Layout>}
                  config={{
                    displayModeBar: true,
                    responsive: true,
                    displaylogo: false,
                    modeBarButtonsToRemove: ["lasso2d", "select2d"],
                    toImageButtonOptions: {
                      format: "png",
                      width: 1200,
                      height: 800,
                    },
                  }}
                  useResizeHandler
                  style={{ width: "100%", height: "100%" }}
                />
              </ChartErrorBoundary>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
