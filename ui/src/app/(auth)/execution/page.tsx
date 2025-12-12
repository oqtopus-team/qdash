"use client";

import { Suspense } from "react";

import { ExecutionPageContent } from "@/components/features/execution/ExecutionPageContent";
import { ExecutionPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function ExecutionPage() {
  return (
    <Suspense fallback={<ExecutionPageSkeleton />}>
      <ExecutionPageContent />
    </Suspense>
  );
}
