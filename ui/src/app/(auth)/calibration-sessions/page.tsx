"use client";

import { Suspense } from "react";

import { CalibrationSessionListPageContent } from "@/components/features/calibration-session/CalibrationSessionListPageContent";

export default function CalibrationSessionsPage() {
  return (
    <Suspense fallback={null}>
      <CalibrationSessionListPageContent />
    </Suspense>
  );
}
