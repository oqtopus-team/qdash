"use client";

import { useParams } from "next/navigation";

import { EvaluationRunDetailPageContent } from "@/components/features/evaluations/EvaluationRunDetailPageContent";

export default function EvaluationRunPage() {
  const params = useParams<{ runId: string }>();
  return <EvaluationRunDetailPageContent runId={params.runId} />;
}
