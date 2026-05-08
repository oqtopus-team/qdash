"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";

import { ForumDetailPage } from "@/components/features/forum/ForumDetailPage";
import { PageContainer } from "@/components/ui/PageContainer";

function ForumDetailSkeleton() {
  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6 flex items-center gap-3">
        <div className="h-8 w-8 bg-base-300 rounded animate-pulse" />
        <div className="h-5 w-56 bg-base-300 rounded animate-pulse" />
      </div>
      <div className="h-40 bg-base-300 rounded-lg animate-pulse mb-4" />
      <div className="h-28 bg-base-300 rounded-lg animate-pulse mb-4" />
      <div className="h-32 bg-base-300 rounded-lg animate-pulse" />
    </div>
  );
}

export default function ForumDetailPageRoute() {
  const params = useParams<{ postId: string }>();

  return (
    <Suspense fallback={<ForumDetailSkeleton />}>
      <PageContainer maxWidth>
        <ForumDetailPage postId={params.postId} />
      </PageContainer>
    </Suspense>
  );
}
