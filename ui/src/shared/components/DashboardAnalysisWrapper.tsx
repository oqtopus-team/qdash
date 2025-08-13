import { IoBarChart, IoTrendingUp, IoStatsChart } from "react-icons/io5";
import {
  EmbeddedAnalysisView,
  CompactAnalysisView,
} from "./EmbeddedAnalysisView";
import { TimeSeriesView } from "@/app/analysis/components/TimeSeriesView";
import { HistogramView } from "@/app/analysis/components/HistogramView";
import { CDFView } from "@/app/analysis/components/CDFView";

/**
 * Dashboard wrapper for TimeSeriesView
 */
export function DashboardTimeSeriesView({
  height = "400px",
  compact = false,
  focusOnPlots = false,
}: {
  height?: string;
  compact?: boolean;
  focusOnPlots?: boolean;
}) {
  const ViewWrapper = compact ? CompactAnalysisView : EmbeddedAnalysisView;

  return (
    <ViewWrapper
      title="Time Series Analysis"
      icon={<IoTrendingUp />}
      navigateTo="/analysis?aview=timeseries"
      height={height}
    >
      <div
        className={`${focusOnPlots ? "dashboard-focus-timeseries" : ""} pointer-events-none overflow-hidden`}
      >
        <TimeSeriesView />
      </div>
    </ViewWrapper>
  );
}

/**
 * Dashboard wrapper for HistogramView
 */
export function DashboardHistogramView({
  height = "400px",
  compact = false,
  focusOnPlots = false,
}: {
  height?: string;
  compact?: boolean;
  focusOnPlots?: boolean;
}) {
  const ViewWrapper = compact ? CompactAnalysisView : EmbeddedAnalysisView;

  return (
    <ViewWrapper
      title="Parameter Distribution"
      icon={<IoBarChart />}
      navigateTo="/analysis?aview=histogram"
      height={height}
    >
      <div
        className={`${focusOnPlots ? "dashboard-focus-histogram" : ""} pointer-events-none overflow-hidden`}
      >
        <HistogramView />
      </div>
    </ViewWrapper>
  );
}

/**
 * Dashboard wrapper for CDFView
 */
export function DashboardCDFView({
  height = "400px",
  compact = false,
  focusOnPlots = false,
}: {
  height?: string;
  compact?: boolean;
  focusOnPlots?: boolean;
}) {
  const ViewWrapper = compact ? CompactAnalysisView : EmbeddedAnalysisView;

  return (
    <ViewWrapper
      title="Parameter CDF"
      icon={<IoStatsChart />}
      navigateTo="/analysis?aview=cdf"
      height={height}
    >
      <div
        className={`${focusOnPlots ? "dashboard-focus-cdf" : ""} pointer-events-none overflow-hidden`}
      >
        <CDFView />
      </div>
    </ViewWrapper>
  );
}

/**
 * Grid layout for multiple dashboard views
 */
interface DashboardAnalysisGridProps {
  views?: ("timeseries" | "histogram" | "cdf")[];
  heights?: Record<string, string>;
  compact?: boolean;
  focusOnPlots?: boolean;
}

export function DashboardAnalysisGrid({
  views = ["timeseries", "histogram", "cdf"],
  heights = {},
  compact = true,
  focusOnPlots = false,
}: DashboardAnalysisGridProps) {
  const defaultHeight = compact ? "300px" : "400px";

  return (
    <div
      className={`grid gap-6 ${
        views.length === 1
          ? "grid-cols-1"
          : views.length === 2
            ? "grid-cols-1 lg:grid-cols-2"
            : "grid-cols-1 lg:grid-cols-2 xl:grid-cols-3"
      }`}
    >
      {views.includes("timeseries") && (
        <DashboardTimeSeriesView
          height={heights.timeseries || defaultHeight}
          compact={compact}
          focusOnPlots={focusOnPlots}
        />
      )}
      {views.includes("histogram") && (
        <DashboardHistogramView
          height={heights.histogram || defaultHeight}
          compact={compact}
          focusOnPlots={focusOnPlots}
        />
      )}
      {views.includes("cdf") && (
        <DashboardCDFView
          height={heights.cdf || defaultHeight}
          compact={compact}
          focusOnPlots={focusOnPlots}
        />
      )}
    </div>
  );
}
