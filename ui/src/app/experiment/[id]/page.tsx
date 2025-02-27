"use client";

import { useParams } from "next/navigation";
import { useFetchAllExecutionsExperiments } from "@/client/execution/execution";
import JsonView from "react18-json-view";
import { useTheme } from "@/app/hooks/useTheme";
import type { ExecutionResponseFigPath } from "@/schemas";

export default function ExecutionDetailPage() {
  const params = useParams();
  const experiment_name = params?.experiment_name as string;
  const timestamp = params?.timestamp as string;
  const { theme } = useTheme();

  const {
    data: executionData,
    isError,
    isLoading,
  } = useFetchAllExecutionsExperiments({
    "experiment_name[]": experiment_name ? [experiment_name] : undefined,
  });

  if (isLoading) {
    return <div>Loading...</div>;
  }
  if (isError) {
    return <div>Error</div>;
  }

  const executionDetail = executionData?.data?.[0];
  if (!executionDetail) {
    return <div>No data found</div>;
  }

  return (
    <div className="w-full px-4">
      <h1 className="text-left text-3xl font-bold px-1 pb-3">
        Execution Detail
      </h1>
      <div className="mb-6">
        <h3 className="text-xl font-semibold mb-2">Figure</h3>
        {executionDetail.fig_path && (
          <img
            src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
              String(executionDetail.fig_path),
            )}`}
            alt="Execution Figure"
            className="w-full h-auto max-h-[60vh] object-contain rounded border border-base-300"
          />
        )}
      </div>
      <div className="mb-6">
        <h3 className="text-xl font-semibold mb-2">Output Parameters</h3>
        <div className="bg-base-200 p-4 rounded-lg">
          <JsonView
            src={executionDetail.output_parameter}
            theme={theme === "dark" ? "vscode" : "default"}
          />
        </div>
      </div>
      <div className="mb-6">
        <h3 className="text-xl font-semibold mb-2">Input Parameters</h3>
        <div className="bg-base-200 p-4 rounded-lg">
          <JsonView
            src={executionDetail.input_parameter}
            theme={theme === "dark" ? "vscode" : "default"}
          />
        </div>
      </div>
    </div>
  );
}
