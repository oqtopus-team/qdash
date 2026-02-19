"use client";

import { Suspense } from "react";

import { CommentsPageContent } from "@/components/features/comments/CommentsPageContent";

function CommentsPageSkeleton() {
  return (
    <div className="w-full min-h-screen bg-base-100/50 px-4 md:px-6 py-6 md:py-8">
      <div className="max-w-[1600px] mx-auto">
        <div className="h-8 w-48 bg-base-300 rounded animate-pulse mb-2" />
        <div className="h-4 w-72 bg-base-300 rounded animate-pulse mb-6" />
        <div className="h-10 w-80 bg-base-300 rounded animate-pulse mb-4" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-32 bg-base-300 rounded-lg animate-pulse"
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function CommentsPage() {
  return (
    <Suspense fallback={<CommentsPageSkeleton />}>
      <CommentsPageContent />
    </Suspense>
  );
}
