import { AgentSessionGraphPageContent } from "@/components/features/execution/AgentSessionGraphPageContent";

interface AgentSessionGraphPageProps {
  params: Promise<{
    chipId: string;
    sessionId: string;
  }>;
}

export default async function AgentSessionGraphPage({ params }: AgentSessionGraphPageProps) {
  const { chipId, sessionId } = await params;

  return <AgentSessionGraphPageContent chipId={chipId} sessionId={sessionId} />;
}
