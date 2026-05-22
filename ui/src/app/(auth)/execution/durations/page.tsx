"use client";

import { Suspense } from "react";

import { ExecutionDurationBreakdownPageContent } from "@/components/features/execution/ExecutionDurationBreakdownPageContent";
import { ExecutionPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function ExecutionDurationsPage() {
  return (
    <Suspense fallback={<ExecutionPageSkeleton />}>
      <ExecutionDurationBreakdownPageContent />
    </Suspense>
  );
}
