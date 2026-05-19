"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";

import { AiReviewRunDetailPageContent } from "@/components/features/ai-reviews/AiReviewRunDetailPageContent";
import { PageContainer } from "@/components/ui/PageContainer";

function AiReviewRunSkeleton() {
  return (
    <PageContainer maxWidth>
      <div className="mb-6 h-9 w-48 animate-pulse rounded bg-base-300" />
      <div className="mb-4 h-20 animate-pulse rounded-lg bg-base-300" />
      <div className="space-y-3">
        <div className="h-64 animate-pulse rounded-lg bg-base-300" />
        <div className="h-64 animate-pulse rounded-lg bg-base-300" />
      </div>
    </PageContainer>
  );
}

export default function AiReviewRunPage() {
  const params = useParams<{ reviewRunId: string }>();

  return (
    <Suspense fallback={<AiReviewRunSkeleton />}>
      <AiReviewRunDetailPageContent reviewRunId={params.reviewRunId} />
    </Suspense>
  );
}
