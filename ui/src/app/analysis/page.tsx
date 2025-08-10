"use client";

import { Suspense } from "react";
import { TimeSeriesView } from "./components/TimeSeriesView";
import { CorrelationView } from "./components/CorrelationView";
import { useAnalysisUrlState } from "@/app/hooks/useUrlState";

type AnalyzeView = "correlation" | "timeseries";

function AnalyzePageContent() {
  // URL state management for view type
  const { analysisViewType, setAnalysisViewType } = useAnalysisUrlState();
  const currentView = (analysisViewType || "correlation") as AnalyzeView;
  const setCurrentView = (view: string) => {
    setAnalysisViewType(view);
  };

  return (
    <div
      className="w-full min-h-screen bg-base-100/50 px-6 py-8"
      style={{ width: "calc(100vw - 20rem)" }}
    >
      <div className="max-w-[1400px] mx-auto space-y-8">
        {/* Header Section */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold mb-2">Chip Analysis</h1>
            <p className="text-base-content/70">
              Analyze and visualize chip parameters
            </p>
          </div>
        </div>

        {/* View Selection Tabs */}
        <div className="tabs tabs-boxed w-fit gap-2 p-2">
          <button
            className={`tab ${
              currentView === "correlation" ? "tab-active" : ""
            }`}
            onClick={() => setCurrentView("correlation")}
          >
            Correlation Plot
          </button>
          <button
            className={`tab ${
              currentView === "timeseries" ? "tab-active" : ""
            }`}
            onClick={() => setCurrentView("timeseries")}
          >
            Time Series
          </button>
        </div>

        {currentView === "correlation" ? (
          <CorrelationView />
        ) : (
          <TimeSeriesView />
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
