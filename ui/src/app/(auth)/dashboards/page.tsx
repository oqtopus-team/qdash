"use client";

import { Suspense } from "react";

import { DashboardListPageContent } from "@/components/features/dashboards/DashboardListPageContent";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function DashboardsPage() {
  return (
    <Suspense fallback={<MetricsPageSkeleton />}>
      <DashboardListPageContent />
    </Suspense>
  );
}
