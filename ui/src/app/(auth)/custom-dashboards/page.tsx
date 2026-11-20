"use client";

import { Suspense } from "react";

import { CustomDashboardListPageContent } from "@/components/features/custom-dashboards/CustomDashboardListPageContent";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function CustomDashboardsPage() {
  return (
    <Suspense fallback={<MetricsPageSkeleton />}>
      <CustomDashboardListPageContent />
    </Suspense>
  );
}
