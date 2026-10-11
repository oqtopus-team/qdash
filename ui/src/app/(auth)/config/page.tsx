"use client";

import { Suspense } from "react";

import { FilesPageContent } from "@/components/features/files/FilesPageContent";
import { EditorPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { CONFIG_WORKSPACE } from "@/lib/fileWorkspace";

export default function ConfigEditorPage() {
  return (
    <Suspense fallback={<EditorPageSkeleton />}>
      <FilesPageContent workspace={CONFIG_WORKSPACE} />
    </Suspense>
  );
}
