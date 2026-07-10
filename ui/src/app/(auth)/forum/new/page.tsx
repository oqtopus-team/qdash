"use client";

import { Suspense } from "react";

import { ForumNewPage } from "@/components/features/forum/ForumNewPage";
import { PageContainer } from "@/components/ui/PageContainer";

function ForumNewSkeleton() {
  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex items-center gap-3">
        <div className="h-8 w-8 animate-pulse rounded bg-base-300" />
        <div className="h-8 w-80 max-w-full animate-pulse rounded bg-base-300" />
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="h-80 animate-pulse rounded-lg bg-base-300" />
        <div className="h-80 animate-pulse rounded-lg bg-base-300" />
      </div>
    </div>
  );
}

export default function ForumNewPageRoute() {
  return (
    <Suspense fallback={<ForumNewSkeleton />}>
      <PageContainer maxWidth>
        <ForumNewPage />
      </PageContainer>
    </Suspense>
  );
}
