"use client";

import { Suspense } from "react";

import { IoAnalytics } from "react-icons/io5";

import { DashboardAnalysisGrid } from "@/shared/components/DashboardAnalysisWrapper";
import { DashboardChipView } from "@/shared/components/DashboardChipWrapper";
import { DashboardExecutionView } from "@/shared/components/DashboardExecutionWrapper";

function DashboardPageContent() {
  return (
    <div
      className="w-full min-h-screen bg-base-100/50 px-6 py-8"
      style={{ width: "calc(100vw - 20rem)" }}
    >
      <div className="max-w-[1400px] mx-auto space-y-8">
        {/* Header Section */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold mb-2">Dashboard</h1>
            <p className="text-base-content/70">
              Monitor quantum calibration systems and performance metrics
            </p>
          </div>
          <div className="text-sm text-base-content/60">
            Last updated:{" "}
            {new Date().toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" })}
          </div>
        </div>

        {/* Chip Experiments - Full Width */}
        <div className="space-y-8">
          <DashboardChipView height="600px" focusOnContent={true} />

          {/* Analysis Overview - Full Width */}
          <div className="space-y-6">
            <h2 className="text-2xl font-semibold flex items-center gap-2">
              <IoAnalytics className="text-primary" />
              Analysis Overview
            </h2>
            <p className="text-base-content/70 mb-6">
              Live views from analysis pages - click any view to expand to full
              analysis
            </p>
            <DashboardAnalysisGrid
              views={["timeseries", "histogram", "cdf"]}
              heights={{
                timeseries: "400px",
                histogram: "400px",
                cdf: "400px",
              }}
              compact={true}
              focusOnPlots={true}
            />
          </div>

          {/* Execution History - Full Width */}
          <DashboardExecutionView height="600px" focusOnContent={true} />
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense
      fallback={
        <div className="w-full flex justify-center py-12">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      }
    >
      <DashboardPageContent />
    </Suspense>
  );
}
