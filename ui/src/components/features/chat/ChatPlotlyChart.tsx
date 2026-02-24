"use client";

import dynamic from "next/dynamic";
import {
  Component,
  type ReactNode,
  useCallback,
  useRef,
  useState,
} from "react";

const Plot = dynamic(() => import("@/components/charts/Plot"), { ssr: false });

interface ChatPlotlyChartProps {
  data: Record<string, unknown>[];
  layout: Record<string, unknown>;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

class ChartErrorBoundary extends Component<
  { children: ReactNode },
  ErrorBoundaryState
> {
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
  const dialogRef = useRef<HTMLDialogElement>(null);

  const openLightbox = useCallback(() => {
    setIsExpanded(true);
    dialogRef.current?.showModal();
  }, []);

  const closeLightbox = useCallback(() => {
    dialogRef.current?.close();
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
            <button
              type="button"
              onClick={openLightbox}
              className="btn btn-xs btn-ghost"
              title="Expand chart"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
                fill="currentColor"
                className="w-4 h-4"
              >
                <path d="M13.28 7.78l3.22-3.22v2.69a.75.75 0 001.5 0v-4.5a.75.75 0 00-.75-.75h-4.5a.75.75 0 000 1.5h2.69l-3.22 3.22a.75.75 0 001.06 1.06zM2 17.25v-4.5a.75.75 0 011.5 0v2.69l3.22-3.22a.75.75 0 011.06 1.06L4.56 16.5h2.69a.75.75 0 010 1.5h-4.5a.75.75 0 01-.75-.75z" />
              </svg>
            </button>
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

      <dialog
        ref={dialogRef}
        className="modal"
        onClose={() => setIsExpanded(false)}
      >
        <div className="modal-box w-11/12 max-w-5xl h-[80vh] flex flex-col p-4">
          <div className="flex justify-between items-center mb-2">
            <h3 className="font-bold text-sm">
              {typeof layout.title === "string"
                ? layout.title
                : (((layout.title as Record<string, unknown>)
                    ?.text as string) ?? "Chart")}
            </h3>
            <button
              type="button"
              onClick={closeLightbox}
              className="btn btn-sm btn-ghost"
            >
              ✕
            </button>
          </div>
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
        </div>
        <form method="dialog" className="modal-backdrop">
          <button type="submit">close</button>
        </form>
      </dialog>
    </>
  );
}
