"use client";

import { Suspense } from "react";
import { ChipPageContent } from "./components/ChipPageContent";

export default function ChipPage() {
  return (
    <Suspense
      fallback={
        <div className="w-full flex justify-center py-12">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      }
    >
      <ChipPageContent />
    </Suspense>
  );
}
