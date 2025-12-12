"use client";

import { Suspense } from "react";

import { ChipPageContent } from "@/components/features/chip/ChipPageContent";
import { ChipPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

export default function ChipPage() {
  return (
    <Suspense fallback={<ChipPageSkeleton />}>
      <ChipPageContent />
    </Suspense>
  );
}
