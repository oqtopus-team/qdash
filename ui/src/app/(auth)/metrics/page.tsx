"use client";

import { Suspense } from "react";

import { MetricsPageContent } from "@/components/features/metrics/MetricsPageContent";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function MetricsPage() {
  return (
    <Suspense fallback={<MetricsPageSkeleton />}>
      <MetricsPageContent />
    </Suspense>
  );
}
