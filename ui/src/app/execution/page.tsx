"use client";

import { Suspense } from "react";

import { ExecutionPageContent } from "./components/ExecutionPageContent";

export default function ExecutionPage() {
  return (
    <Suspense
      fallback={
        <div className="w-full flex justify-center py-12">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      }
    >
      <ExecutionPageContent />
    </Suspense>
  );
}
