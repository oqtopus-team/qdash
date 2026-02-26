"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { PageContainer } from "@/components/ui/PageContainer";
import { TaskKnowledgeDetailPage } from "@/components/features/task-knowledge/TaskKnowledgeDetailPage";

function DetailSkeleton() {
  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <div className="h-8 w-8 bg-base-300 rounded-full animate-pulse" />
        <div className="h-6 bg-base-300 rounded w-64 animate-pulse" />
      </div>
      <div className="space-y-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-24 bg-base-300 rounded-lg animate-pulse" />
        ))}
      </div>
    </div>
  );
}

export default function TaskKnowledgeDetailRoute() {
  const params = useParams<{ taskName: string }>();
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <PageContainer maxWidth>
        <TaskKnowledgeDetailPage taskName={params.taskName} />
      </PageContainer>
    </Suspense>
  );
}
