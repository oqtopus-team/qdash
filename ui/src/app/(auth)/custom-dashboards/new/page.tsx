"use client";

import { Suspense } from "react";

import { CustomDashboardPageContent } from "@/components/features/custom-dashboards/CustomDashboardPageContent";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function NewCustomDashboardPage() {
  return (
    <Suspense fallback={<MetricsPageSkeleton />}>
      <CustomDashboardPageContent dashboardId={null} />
    </Suspense>
  );
}
