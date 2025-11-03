"use client";

import { Suspense } from "react";

import { MetricsPageContent } from "./components/MetricsPageContent";

export default function MetricsPage() {
  return (
    <Suspense
      fallback={
        <div className="w-full flex justify-center py-12">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      }
    >
      <MetricsPageContent />
    </Suspense>
  );
}
