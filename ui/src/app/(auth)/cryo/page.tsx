"use client";

import { Suspense } from "react";

import { CryoPageContent } from "@/components/features/cryo/CryoPageContent";
import { MetricsPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function CryoPage() {
  return (
    <Suspense fallback={<MetricsPageSkeleton />}>
      <CryoPageContent />
    </Suspense>
  );
}
