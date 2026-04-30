"use client";

import { Suspense } from "react";

import { ImportPageContent } from "@/components/features/import/ImportPageContent";

function ImportPageSkeleton() {
  return (
    <div className="p-6 space-y-6">
      <div className="skeleton h-8 w-64"></div>
      <div className="skeleton h-4 w-96"></div>
      <div className="skeleton h-96 w-full"></div>
    </div>
  );
}

export default function ImportPage() {
  return (
    <Suspense fallback={<ImportPageSkeleton />}>
      <ImportPageContent />
    </Suspense>
  );
}
