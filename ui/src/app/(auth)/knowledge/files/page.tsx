"use client";

import { Suspense } from "react";

import { FilesPageContent } from "@/components/features/files/FilesPageContent";
import { EditorPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { KNOWLEDGE_WORKSPACE } from "@/lib/fileWorkspace";

export default function KnowledgeFilesPage() {
  return (
    <Suspense fallback={<EditorPageSkeleton />}>
      <FilesPageContent workspace={KNOWLEDGE_WORKSPACE} />
    </Suspense>
  );
}
