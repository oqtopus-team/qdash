"use client";

import { Suspense } from "react";

import { useParams } from "next/navigation";

import { CalibrationSessionPageContent } from "@/components/features/calibration-session/CalibrationSessionPageContent";

export default function CalibrationSessionPage() {
  const params = useParams<{ calibrationSessionId: string }>();
  return (
    <Suspense fallback={null}>
      <CalibrationSessionPageContent calibrationSessionId={params.calibrationSessionId} />
    </Suspense>
  );
}
