"use client";

import { Suspense } from "react";

import { DashboardPageContent } from "@/components/features/dashboards/DashboardPageContent";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function NewDashboardPage() {
  return (
    <Suspense fallback={<MetricsPageSkeleton />}>
      <DashboardPageContent dashboardId={null} />
    </Suspense>
  );
}
