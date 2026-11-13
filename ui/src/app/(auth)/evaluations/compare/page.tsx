"use client";

import { Suspense } from "react";

import { EvaluationComparePageContent } from "@/components/features/evaluations/EvaluationComparePageContent";

export default function EvaluationComparePage() {
  // The page reads its two runs from the query string.
  return (
    <Suspense fallback={null}>
      <EvaluationComparePageContent />
    </Suspense>
  );
}
