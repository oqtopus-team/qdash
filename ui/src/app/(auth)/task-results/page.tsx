"use client";

import { Suspense } from "react";

import { TaskResultsPageContent } from "@/components/features/task-results/TaskResultsPageContent";

function TaskResultsPageSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="mb-2 h-8 w-48 animate-pulse rounded bg-base-300" />
          <div className="h-4 w-80 animate-pulse rounded bg-base-300" />
        </div>
        <div className="h-6 w-24 animate-pulse rounded bg-base-300" />
      </div>
      <div className="h-24 animate-pulse rounded-lg bg-base-300" />
      <div className="h-96 animate-pulse rounded-lg bg-base-300" />
    </div>
  );
}

export default function TaskResultsPage() {
  return (
    <Suspense fallback={<TaskResultsPageSkeleton />}>
      <TaskResultsPageContent />
    </Suspense>
  );
}
