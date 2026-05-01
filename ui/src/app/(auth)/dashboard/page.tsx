"use client";

import { Suspense } from "react";

import { DashboardPageContent } from "@/components/features/dashboard/DashboardPageContent";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function DashboardPage() {
  return (
    <Suspense fallback={<MetricsPageSkeleton />}>
      <DashboardPageContent />
    </Suspense>
  );
}
