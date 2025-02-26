import ExecutionDetailClient from "./client";

interface ExecutionDetailPageProps {
  params: {
    chip_id: string;
    execute_id: string;
  };
}

export default function ExecutionDetailPage({
  params,
}: ExecutionDetailPageProps) {
  const { chip_id, execute_id } = params;

  return <ExecutionDetailClient chip_id={chip_id} execute_id={execute_id} />;
}
