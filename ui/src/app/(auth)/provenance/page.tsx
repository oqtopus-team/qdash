"use client";

import { Suspense } from "react";

import { ProvenancePageContent } from "@/components/features/provenance/ProvenancePageContent";

function ProvenancePageSkeleton() {
  return (
    <div className="p-6 space-y-6">
      <div className="skeleton h-8 w-64"></div>
      <div className="skeleton h-4 w-96"></div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="skeleton h-96 w-full"></div>
        <div className="skeleton h-96 w-full"></div>
      </div>
    </div>
  );
}

export default function ProvenancePage() {
  return (
    <Suspense fallback={<ProvenancePageSkeleton />}>
      <ProvenancePageContent />
    </Suspense>
  );
}
