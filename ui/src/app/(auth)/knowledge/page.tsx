"use client";

import { Suspense } from "react";
import { TaskKnowledgePageContent } from "@/components/features/task-knowledge/TaskKnowledgePageContent";

function TaskKnowledgeSkeleton() {
  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="h-8 bg-base-300 rounded w-48 mb-2 animate-pulse" />
      <div className="h-4 bg-base-300 rounded w-96 mb-6 animate-pulse" />
      <div className="h-10 bg-base-300 rounded w-64 mb-4 animate-pulse" />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div key={i} className="h-28 bg-base-300 rounded-lg animate-pulse" />
        ))}
      </div>
    </div>
  );
}

export default function TaskKnowledgePage() {
  return (
    <Suspense fallback={<TaskKnowledgeSkeleton />}>
      <TaskKnowledgePageContent />
    </Suspense>
  );
}
