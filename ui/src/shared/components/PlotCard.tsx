import { ReactNode, useMemo } from "react";
import dynamic from "next/dynamic";
import type { PlotData, Layout, Config } from "plotly.js";

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
  plotData: Partial<PlotData>[];
  layout: Partial<Layout>;
  config?: Partial<Config>;
  height?: string;
  className?: string;
  children?: ReactNode; // For additional content like controls
}

/**
 * Reusable Plotly visualization container with consistent styling and states
 */
export function PlotCard({
  title,
  icon,
  isLoading = false,
  hasData = true,
  emptyStateMessage = "No data available",
  plotData,
  layout,
  config,
  height = "550px",
  className = "",
  children,
}: PlotCardProps) {
  const defaultConfig = useMemo(
    () => ({
      displaylogo: false,
      responsive: true,
      toImageButtonOptions: {
        format: "svg" as const,
        filename: "plot_export",
        height: 600,
        width: 800,
        scale: 2,
      },
    }),
    [],
  );

  const mergedConfig = useMemo(
    () => ({
      ...defaultConfig,
      ...config,
    }),
    [defaultConfig, config],
  );

  return (
    <div
      className={`card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300 ${className}`}
    >
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold flex items-center gap-2">
          {icon}
          {title}
        </h2>
        {children}
      </div>

      <div
        className="w-full bg-base-200/50 rounded-xl p-4 relative"
        style={{ height }}
      >
        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center h-full absolute inset-0 z-10">
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

        {/* Plot area */}
        {!isLoading && hasData && plotData.length > 0 && (
          <Plot
            data={plotData}
            layout={layout}
            config={mergedConfig}
            style={{ width: "100%", height: "100%" }}
            useResizeHandler={true}
          />
        )}
      </div>
    </div>
  );
}
