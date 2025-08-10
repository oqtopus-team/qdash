import { ReactNode } from "react";
import dynamic from "next/dynamic";

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full">
      <div className="loading loading-spinner loading-lg text-primary"></div>
    </div>
  ),
});

interface PlotCardProps {
  title: string;
  icon?: ReactNode;
  isLoading?: boolean;
  hasData?: boolean;
  emptyStateMessage?: string;
  plotData?: any[];
  layout?: any;
  config?: any;
  height?: string;
  children?: ReactNode;
}

export function PlotCard({
  title,
  icon,
  isLoading = false,
  hasData = false,
  emptyStateMessage = "No data available",
  plotData = [],
  layout = {},
  config = {},
  height = "550px",
  children,
}: PlotCardProps) {
  const defaultConfig = {
    displaylogo: false,
    responsive: true,
    toImageButtonOptions: {
      format: "svg" as const,
      filename: "chart",
      height: 600,
      width: 800,
      scale: 2,
    },
    ...config,
  };

  return (
    <div className="card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
      <h2 className="text-2xl font-semibold mb-6 text-center flex items-center justify-center gap-2">
        {icon}
        {title}
      </h2>
      <div
        className="w-full bg-base-200/50 rounded-xl p-4"
        style={{ height }}
      >
        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center h-full">
            <div className="loading loading-spinner loading-lg text-primary"></div>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !hasData && (
          <div className="flex items-center justify-center h-full text-base-content/70">
            <div className="text-center">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-12 h-12 mx-auto mb-4 opacity-50"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M3 3v18h18"></path>
                <path d="M3 12h18"></path>
                <path d="M12 3v18"></path>
              </svg>
              <p className="text-lg">{emptyStateMessage}</p>
            </div>
          </div>
        )}

        {/* Plot */}
        {!isLoading && hasData && plotData.length > 0 && (
          <Plot
            data={plotData}
            layout={layout}
            config={defaultConfig}
            style={{ width: "100%", height: "100%" }}
            useResizeHandler={true}
          />
        )}

        {/* Custom content */}
        {children}
      </div>
    </div>
  );
}