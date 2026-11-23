"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";

import { DashboardPageContent } from "@/components/features/dashboards/DashboardPageContent";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function DashboardPage() {
  const params = useParams<{ dashboardId: string }>();

  return (
    <Suspense fallback={<MetricsPageSkeleton />}>
      <DashboardPageContent dashboardId={params.dashboardId} />
    </Suspense>
  );
}
