"use client";

import { Suspense } from "react";

import { useListChips } from "@/client/chip/chip";
import { CDFView } from "@/components/features/analysis/CDFView";
import { CorrelationView } from "@/components/features/analysis/CorrelationView";
import { HistogramView } from "@/components/features/analysis/HistogramView";
import { TimeSeriesView } from "@/components/features/analysis/TimeSeriesView";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { AnalysisPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { ViewSwitch } from "@/components/ui/ViewSwitch";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { useAnalysisUrlState } from "@/hooks/useUrlState";

type AnalyzeView = "timeseries" | "histogram" | "cdf" | "correlation";

function AnalyzePageContent() {
  // URL state management for view type
  const { analysisViewType, setAnalysisViewType, isInitialized } = useAnalysisUrlState();
  const currentView = (analysisViewType || "timeseries") as AnalyzeView;
  const setCurrentView = (view: string) => {
    setAnalysisViewType(view);
  };

  // Check loading state for initial skeleton
  const { isLoading: isChipsLoading } = useListChips();
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
          title="Analysis"
          description="Time series, histograms, CDFs and correlations of chip parameters"
        />

        <ViewSwitch
          ariaLabel="Analysis view"
          className="overflow-x-auto"
          value={currentView}
          onValueChange={setCurrentView}
          items={[
            { value: "timeseries", label: "Time Series" },
            { value: "histogram", label: "Histogram" },
            { value: "cdf", label: "CDF" },
            { value: "correlation", label: "Correlation" },
          ]}
        />

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
