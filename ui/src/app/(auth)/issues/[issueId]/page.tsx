"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";

import { PageContainer } from "@/components/ui/PageContainer";
import { IssueDetailPage } from "@/components/features/issues/IssueDetailPage";

function IssueSkeleton() {
  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <div className="h-8 w-8 bg-base-300 rounded animate-pulse" />
        <div className="h-5 w-40 bg-base-300 rounded animate-pulse" />
      </div>
      <div className="h-32 bg-base-300 rounded-lg animate-pulse mb-4" />
      <div className="h-48 bg-base-300 rounded-lg animate-pulse mb-4" />
      <div className="h-24 bg-base-300 rounded-lg animate-pulse" />
    </div>
  );
}

export default function IssueDetailPageRoute() {
  const params = useParams<{ issueId: string }>();

  return (
    <Suspense fallback={<IssueSkeleton />}>
      <PageContainer maxWidth>
        <IssueDetailPage commentId={params.issueId} />
      </PageContainer>
    </Suspense>
  );
}
