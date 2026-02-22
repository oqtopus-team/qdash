import { ExecutionDetailClient } from "@/components/features/execution/ExecutionClient";

interface ExecutionDetailPageProps {
  params: Promise<{
    chip_id: string;
    execute_id: string;
  }>;
}

export default async function ExecutionDetailPage({
  params,
}: ExecutionDetailPageProps) {
  const { chip_id, execute_id } = await params;

  return <ExecutionDetailClient chip_id={chip_id} execute_id={execute_id} />;
}
