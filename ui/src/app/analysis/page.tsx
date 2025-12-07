"use client";

import { Suspense } from "react";

import { CDFView } from "./components/CDFView";
import { CorrelationView } from "./components/CorrelationView";
import { HistogramView } from "./components/HistogramView";
import { TimeSeriesView } from "./components/TimeSeriesView";

import { useAnalysisUrlState } from "@/app/hooks/useUrlState";

type AnalyzeView = "timeseries" | "histogram" | "cdf" | "correlation";

function AnalyzePageContent() {
  // URL state management for view type
  const { analysisViewType, setAnalysisViewType } = useAnalysisUrlState();
  const currentView = (analysisViewType || "timeseries") as AnalyzeView;
  const setCurrentView = (view: string) => {
    setAnalysisViewType(view);
  };

  return (
    <div className="w-full min-h-screen bg-base-100/50 px-3 sm:px-6 py-4 sm:py-8">
      <div className="max-w-[1400px] mx-auto space-y-4 sm:space-y-8">
        {/* Header Section */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-4 sm:mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold mb-1 sm:mb-2">
              Chip Analysis
            </h1>
            <p className="text-sm sm:text-base text-base-content/70">
              Analyze and visualize chip parameters
            </p>
          </div>
        </div>

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
    </div>
  );
}

export default function AnalyzePage() {
  return (
    <Suspense
      fallback={
        <div className="w-full flex justify-center py-12">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      }
    >
      <AnalyzePageContent />
    </Suspense>
  );
}
