"use client";

import { Suspense } from "react";

import { OverviewPageContent } from "@/components/features/overview/OverviewPageContent";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function OverviewPage() {
  return (
    <Suspense fallback={<MetricsPageSkeleton />}>
      <OverviewPageContent />
    </Suspense>
  );
}
