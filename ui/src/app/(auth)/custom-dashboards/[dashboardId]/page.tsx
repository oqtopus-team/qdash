"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";

import { CustomDashboardPageContent } from "@/components/features/custom-dashboards/CustomDashboardPageContent";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function CustomDashboardPage() {
  const params = useParams<{ dashboardId: string }>();

  return (
    <Suspense fallback={<MetricsPageSkeleton />}>
      <CustomDashboardPageContent dashboardId={params.dashboardId} />
    </Suspense>
  );
}
