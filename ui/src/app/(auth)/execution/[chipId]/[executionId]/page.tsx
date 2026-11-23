import { Suspense } from "react";

import { ExecutionDetailClient } from "@/components/features/execution/ExecutionClient";
import { ExecutionDetailPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

interface ExecutionDetailPageProps {
  params: Promise<{
    chipId: string;
    executionId: string;
  }>;
}

export default async function ExecutionDetailPage({ params }: ExecutionDetailPageProps) {
  const { chipId, executionId } = await params;

  // The page reads the Executions list view it links back to from the query string.
  return (
    <Suspense fallback={<ExecutionDetailPageSkeleton />}>
      <ExecutionDetailClient chipId={chipId} executionId={executionId} />
    </Suspense>
  );
}
