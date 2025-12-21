"use client";

import { Suspense } from "react";

import { useListChipsSummary } from "@/client/chip/chip";
import { CDFView } from "@/components/features/analysis/CDFView";
import { CorrelationView } from "@/components/features/analysis/CorrelationView";
import { HistogramView } from "@/components/features/analysis/HistogramView";
import { TimeSeriesView } from "@/components/features/analysis/TimeSeriesView";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { AnalysisPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { useAnalysisUrlState } from "@/hooks/useUrlState";

type AnalyzeView = "timeseries" | "histogram" | "cdf" | "correlation";

function AnalyzePageContent() {
  // URL state management for view type
  const { analysisViewType, setAnalysisViewType, isInitialized } =
    useAnalysisUrlState();
  const currentView = (analysisViewType || "timeseries") as AnalyzeView;
  const setCurrentView = (view: string) => {
    setAnalysisViewType(view);
  };

  // Check loading state for initial skeleton
  const { isLoading: isChipsLoading } = useListChipsSummary();
  const { isLoading: isConfigLoading } = useMetricsConfig();

  // Show skeleton during initial loading
  if (!isInitialized || isChipsLoading || isConfigLoading) {
    return <AnalysisPageSkeleton />;
  }

  return (
    <PageContainer maxWidth>
      <div className="space-y-4 sm:space-y-8">
        {/* Header Section */}
        <PageHeader
          title="Chip Analysis"
          description="Analyze and visualize chip parameters"
        />

        {/* View Selection Tabs */}
        <div className="tabs tabs-boxed w-full sm:w-fit gap-1 sm:gap-2 p-1 sm:p-2 overflow-x-auto flex-nowrap">
          <button
            className={`tab tab-sm sm:tab-md whitespace-nowrap ${
              currentView === "timeseries" ? "tab-active" : ""
            }`}
            onClick={() => setCurrentView("timeseries")}
          >
            Time Series
          </button>
          <button
            className={`tab tab-sm sm:tab-md whitespace-nowrap ${currentView === "histogram" ? "tab-active" : ""}`}
            onClick={() => setCurrentView("histogram")}
          >
            Histogram
          </button>
          <button
            className={`tab tab-sm sm:tab-md whitespace-nowrap ${currentView === "cdf" ? "tab-active" : ""}`}
            onClick={() => setCurrentView("cdf")}
          >
            CDF
          </button>
          <button
            className={`tab tab-sm sm:tab-md whitespace-nowrap ${
              currentView === "correlation" ? "tab-active" : ""
            }`}
            onClick={() => setCurrentView("correlation")}
          >
            Correlation
          </button>
        </div>

        {currentView === "timeseries" ? (
          <TimeSeriesView />
        ) : currentView === "histogram" ? (
          <HistogramView />
        ) : currentView === "cdf" ? (
          <CDFView />
        ) : (
          <CorrelationView />
        )}
      </div>
    </PageContainer>
  );
}

export default function AnalyzePage() {
  return (
    <Suspense fallback={<AnalysisPageSkeleton />}>
      <AnalyzePageContent />
    </Suspense>
  );
}
