"use client";

import { useParams } from "next/navigation";

import { AgentInterventionPageContent } from "@/components/features/agent-session/AgentInterventionPageContent";

export default function AgentInterventionPage() {
  const params = useParams<{ sessionId: string; interventionId: string }>();
  return (
    <AgentInterventionPageContent
      sessionId={params.sessionId}
      interventionId={params.interventionId}
    />
  );
}
