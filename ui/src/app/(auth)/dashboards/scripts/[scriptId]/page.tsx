"use client";

import { useParams } from "next/navigation";

import { MetricScriptEditorPageContent } from "@/components/features/metric-scripts/MetricScriptEditorPageContent";

export default function MetricScriptEditorPage() {
  const params = useParams<{ scriptId: string }>();

  return <MetricScriptEditorPageContent scriptId={params.scriptId} />;
}
