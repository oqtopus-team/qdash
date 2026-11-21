import { AgentSessionJourneyPageContent } from "@/components/features/execution/AgentSessionJourneyPageContent";

interface AgentSessionJourneyPageProps {
  params: Promise<{
    chipId: string;
    sessionId: string;
  }>;
}

export default async function AgentSessionJourneyPage({ params }: AgentSessionJourneyPageProps) {
  const { chipId, sessionId } = await params;

  return <AgentSessionJourneyPageContent chipId={chipId} sessionId={sessionId} />;
}
