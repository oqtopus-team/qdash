import { ExecutionDetailClient } from "@/components/features/execution/ExecutionClient";

interface ExecutionDetailPageProps {
  params: Promise<{
    chipId: string;
    executionId: string;
  }>;
}

export default async function ExecutionDetailPage({
  params,
}: ExecutionDetailPageProps) {
  const { chipId, executionId } = await params;

  return <ExecutionDetailClient chipId={chipId} executionId={executionId} />;
}
