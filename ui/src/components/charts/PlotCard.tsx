import dynamic from "next/dynamic";
import type { ReactNode } from "react";
import { useMemo, useState, useEffect } from "react";

import type { PlotData, Layout, Config } from "plotly.js";

const Plot = dynamic(() => import("@/components/charts/Plot"), {
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
  mobileHeight?: string;
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
  mobileHeight = "350px",
  className = "",
  children,
}: PlotCardProps) {
  // Track if mobile for layout adjustments
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 640);
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  // Adjust layout for mobile (hide legend, reduce margins)
  const responsiveLayout = useMemo<Partial<Layout>>(() => {
    if (!isMobile) return layout;

    return {
      ...layout,
      showlegend: false,
      margin: { l: 50, r: 20, t: 40, b: 60 },
      title: layout.title
        ? typeof layout.title === "string"
          ? { text: layout.title, font: { size: 14 } }
          : {
              ...layout.title,
              font: { ...(layout.title as any).font, size: 14 },
            }
        : undefined,
    };
  }, [layout, isMobile]);

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
      className={`card bg-base-100 shadow-xl rounded-xl p-4 sm:p-8 border border-base-300 ${className}`}
    >
      <div className="flex items-center justify-between mb-4 sm:mb-6">
        <h2 className="text-lg sm:text-2xl font-semibold flex items-center gap-2">
          {icon}
          {title}
        </h2>
        {children}
      </div>

      {/* Mobile height */}
      <div
        className="w-full bg-base-200/50 rounded-xl p-2 sm:p-4 relative sm:hidden"
        style={{ height: mobileHeight }}
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
                className="w-8 h-8 mx-auto mb-2 opacity-50"
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
              <p className="text-sm">{emptyStateMessage}</p>
            </div>
          </div>
        )}

        {/* Plot area */}
        {!isLoading && hasData && plotData.length > 0 && (
          <Plot
            data={plotData}
            layout={responsiveLayout}
            config={mergedConfig}
            style={{ width: "100%", height: "100%" }}
            useResizeHandler={true}
          />
        )}
      </div>

      {/* Desktop height */}
      <div
        className="w-full bg-base-200/50 rounded-xl p-4 relative hidden sm:block"
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
