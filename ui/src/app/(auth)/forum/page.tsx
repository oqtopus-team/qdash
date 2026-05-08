"use client";

import { Suspense } from "react";

import { ForumPageContent } from "@/components/features/forum/ForumPageContent";

function ForumPageSkeleton() {
  return (
    <div className="w-full min-h-screen bg-base-100/50 px-4 md:px-6 py-6 md:py-8">
      <div className="max-w-[1600px] mx-auto">
        <div className="h-8 w-48 bg-base-300 rounded animate-pulse mb-2" />
        <div className="h-4 w-96 max-w-full bg-base-300 rounded animate-pulse mb-6" />
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5 mb-4">
          {[1, 2, 3, 4, 5].map((item) => (
            <div
              key={item}
              className="h-24 bg-base-300 rounded-lg animate-pulse"
            />
          ))}
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map((item) => (
            <div
              key={item}
              className="h-32 bg-base-300 rounded-lg animate-pulse"
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ForumPage() {
  return (
    <Suspense fallback={<ForumPageSkeleton />}>
      <ForumPageContent />
    </Suspense>
  );
}
