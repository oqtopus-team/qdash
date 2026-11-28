"use client";

import { useParams } from "next/navigation";

import { AgentSessionPageContent } from "@/components/features/agent-session/AgentSessionPageContent";

export default function AgentSessionPage() {
  const params = useParams<{ sessionId: string }>();
  return <AgentSessionPageContent sessionId={params.sessionId} />;
}
