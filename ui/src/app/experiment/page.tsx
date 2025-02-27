"use client";
import {
  useFetchAllExecutionsExperiments,
  useFetchAllExecutions,
} from "@/client/execution/execution";
import type { ExecutionResponse, ExecutionResponseStatus } from "@/schemas";
import { useFetchAllExperiment } from "@/client/experiment/experiment";
import type {
  ExperimentResponse,
  FetchAllExecutionsExperimentsParams,
} from "@/schemas";
import { useEffect, useState } from "react";
import JsonView from "react18-json-view";
import Select from "react-select";

const labelOptions = Array.from({ length: 64 }, (_, i) => ({
  value: `Q${i}`,
  label: `Q${i}`,
}));

function ExperimentPage() {
  const [selectedLabels, setSelectedLabels] = useState<
    { value: string; label: string }[]
  >([]);
  const [selectedExperiments, setSelectedExperiments] = useState<
    { value: string; label: string }[]
  >([]);
  const [selectedExecutionIds, setSelectedExecutionIds] = useState<
    { value: string; label: string }[]
  >([]);

  // ロギング用のクエリパラメータ
  const queryParams: FetchAllExecutionsExperimentsParams = {
    "label[]": selectedLabels.map((option) => option.value),
    "experiment_name[]": selectedExperiments.map((option) => option.value),
    "execution_id[]": selectedExecutionIds.map((option) => option.value),
  };

  // クエリパラメータをコンソールに出力
  console.log("Query Params:", queryParams);

  const {
    data: executionData,
    isError,
    isLoading,
    refetch,
  } = useFetchAllExecutionsExperiments(queryParams);

  const { data: experimentData } = useFetchAllExperiment();
  const { data: allExecutionsData } = useFetchAllExecutions();
  const [cardData, setCardData] = useState<ExecutionResponse[]>([]);
  const [selectedExecutionKey, setSelectedExecutionKey] = useState<
    string | null
  >(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  // Set up initial data fetch and periodic polling
  useEffect(() => {
    if (executionData) {
      setCardData(executionData.data);
    }
  }, [executionData]);

  // Polling logic to refresh data every 10 seconds
  useEffect(() => {
    const intervalId = setInterval(() => {
      refetch(); // Trigger refetching of data
    }, 10000); // 10 seconds

    return () => clearInterval(intervalId); // Cleanup on unmount
  }, [refetch]);

  if (isLoading) {
    return <div>Loading...</div>;
  }
  if (isError) {
    return <div>Error</div>;
  }

  // Generate a unique key for each execution
  const getExecutionKey = (execution: ExecutionResponse): string =>
    `${execution.experiment_name}-${new Date(
      execution.timestamp,
    ).toISOString()}`;

  const handleCardClick = (execution: ExecutionResponse) => {
    setSelectedExecutionKey(getExecutionKey(execution));
    setIsSidebarOpen(true);
  };

  const handleCloseSidebar = () => {
    setIsSidebarOpen(false);
    setSelectedExecutionKey(null);
  };

  // Function to determine the left border color based on status
  const getStatusBorderStyle = (status: ExecutionResponseStatus): string => {
    switch (status) {
      case "running":
        return "border-l-4 border-info";
      case "success":
        return "border-l-4 border-success";
      case "failed":
        return "border-l-4 border-error";
      default:
        return "border-l-4 border-base-300";
    }
  };

  const experimentOptions =
    experimentData?.data.map((experiment: ExperimentResponse) => ({
      value: experiment.experiment_name,
      label: experiment.experiment_name,
    })) || [];

  const executionIdOptions =
    allExecutionsData?.data.map((execution) => ({
      value: execution.execution_id,
      label: execution.execution_id,
    })) || [];

  return (
    <div
      className="w-full px-4 relative"
      style={{ width: "calc(100vw - 20rem)" }}
    >
      <h1 className="text-left text-3xl font-bold px-1 pb-3">
        Execution History
      </h1>
      <div className="mb-4 flex justify-start space-x-4">
        <Select
          isMulti
          options={labelOptions}
          value={selectedLabels}
          onChange={(newValue) =>
            setSelectedLabels(newValue as { value: string; label: string }[])
          }
          placeholder="Filter by label"
          className="w-1/5"
        />
        <Select
          isMulti
          options={experimentOptions}
          value={selectedExperiments}
          onChange={(newValue) =>
            setSelectedExperiments(
              newValue as { value: string; label: string }[],
            )
          }
          placeholder="Filter by experiment"
          className="w-1/4"
        />
        <Select
          isMulti
          options={executionIdOptions}
          value={selectedExecutionIds}
          onChange={(newValue) =>
            setSelectedExecutionIds(
              newValue as { value: string; label: string }[],
            )
          }
          placeholder="Filter by execution ID"
          className="w-1/4"
        />
      </div>
      <div className="grid grid-cols-1 gap-2 mx-5">
        {cardData.map((execution, index) => {
          const executionKey = getExecutionKey(execution);
          const isSelected = selectedExecutionKey === executionKey;
          const statusBorderStyle = getStatusBorderStyle(
            execution.status ?? "failed",
          );

          return (
            <div
              key={index}
              className={`p-4 rounded-lg shadow-md flex cursor-pointer relative overflow-hidden transition-transform duration-200 bg-base-100 ${
                isSelected ? "transform scale-100" : "transform scale-95"
              } ${statusBorderStyle}`}
              onClick={() => handleCardClick(execution)}
            >
              {isSelected && (
                <div className="absolute inset-0 bg-primary opacity-10 pointer-events-none transition-opacity duration-500" />
              )}
              <div className="relative z-10">
                <h2 className="text-xl font-semibold mb-1">
                  {execution.label} - {execution.experiment_name}
                </h2>
                <div className="flex items-center mb-1">
                  <p className="text-sm text-base-content/60 mr-4">
                    {new Date(execution.timestamp).toLocaleString()}
                  </p>
                  <span
                    className={`text-sm font-semibold ${
                      execution.status === "running"
                        ? "text-info"
                        : execution.status === "success"
                          ? "text-success"
                          : "text-error"
                    }`}
                  >
                    {execution.status === "running"
                      ? "Running"
                      : execution.status === "success"
                        ? "Success"
                        : "Failed"}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Sidebar */}
      <div
        className={`fixed right-0 top-0 w-1/2 h-full bg-base-100 shadow-lg border-l overflow-y-auto p-6 transition-transform duration-300 ${
          isSidebarOpen
            ? "transform translate-x-0"
            : "transform translate-x-full"
        }`}
        style={{ maxWidth: "40%" }}
      >
        <button
          onClick={handleCloseSidebar}
          className="text-base-content/60 text-2xl font-bold absolute top-4 right-4 hover:text-base-content"
        >
          ×
        </button>
        {selectedExecutionKey && (
          <>
            <button className="btn btn-primary mb-4">Open in New Page</button>
            <h2 className="text-2xl font-bold mb-6">
              {selectedExecutionKey.replace("-", " - ")}
            </h2>
            {cardData.find(
              (exec) => getExecutionKey(exec) === selectedExecutionKey,
            )?.fig_path && (
              <div className="mb-6">
                <h3 className="text-xl font-semibold mb-2">Figure</h3>
                <img
                  src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                    cardData.find(
                      (exec) => getExecutionKey(exec) === selectedExecutionKey,
                    )?.fig_path ?? "",
                  )}`}
                  alt="Execution Figure"
                  className="w-full h-auto max-h-[60vh] object-contain rounded border"
                />
              </div>
            )}
            <div className="mb-6">
              <h3 className="text-xl font-semibold mb-2">Output Parameters</h3>
              <div className="bg-base-200 p-4 rounded-lg">
                <JsonView
                  src={
                    cardData.find(
                      (exec) => getExecutionKey(exec) === selectedExecutionKey,
                    )?.output_parameter
                  }
                  theme="vscode"
                />
              </div>
            </div>
            <div className="mb-6">
              <h3 className="text-xl font-semibold mb-2">Input Parameters</h3>
              <div className="bg-base-200 p-4 rounded-lg">
                <JsonView
                  src={
                    cardData.find(
                      (exec) => getExecutionKey(exec) === selectedExecutionKey,
                    )?.input_parameter
                  }
                  theme="vscode"
                />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default ExperimentPage;
