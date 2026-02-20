"use client";

import dynamic from "next/dynamic";
import { Component, type ReactNode } from "react";

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
  const mergedLayout = {
    autosize: true,
    height: 300,
    margin: { l: 50, r: 20, t: 40, b: 40 },
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { size: 11 },
    ...layout,
  };

  return (
    <ChartErrorBoundary>
      <div className="w-full my-2 rounded-lg border border-base-300 overflow-hidden">
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
  );
}
