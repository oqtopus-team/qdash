"use client";

import { useFetchExecutionByChipId } from "@/client/chip/chip";
import { FaExternalLinkAlt } from "react-icons/fa";
import JsonView from "react18-json-view";
import { ExecutionResponseDetail } from "@/schemas";
import ExecutionDAG from "./ExecutionDAG";

interface ExecutionDetailClientProps {
  chip_id: string;
  execute_id: string;
}

export default function ExecutionDetailClient({
  chip_id,
  execute_id,
}: ExecutionDetailClientProps) {
  const {
    data: executionDetailData,
    isLoading: isDetailLoading,
    isError: isDetailError,
  } = useFetchExecutionByChipId(chip_id, execute_id);

  const getStatusBorderStyle = (status: string) => {
    switch (status) {
      case "running":
        return "border-l-4 border-info";
      case "completed":
        return "border-l-4 border-success";
      case "scheduled":
        return "border-l-4 border-warning";
      case "failed":
        return "border-l-4 border-error";
      default:
        return "border-l-4 border-base-300";
    }
  };

  if (isDetailLoading) return <div>Loading...</div>;
  if (isDetailError) return <div>Error loading execution details.</div>;
  if (!executionDetailData) return <div>No data found.</div>;

  const { data: execution } = executionDetailData as {
    data: ExecutionResponseDetail;
  };

  return (
    <div className="w-full px-4 py-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex justify-between items-center">
          <h1 className="text-3xl font-bold">{execution.name}</h1>
          <div className="flex space-x-4">
            <a
              href={`/execution/${execute_id}/experiment`}
              className="bg-neutral text-neutral-content px-4 py-2 rounded flex items-center hover:opacity-80 transition-colors"
            >
              <FaExternalLinkAlt className="mr-2" />
              Go to Experiment
            </a>
            <a
              href={(execution.note as { [key: string]: any })?.ui_url || "#"}
              className="bg-accent text-accent-content px-4 py-2 rounded flex items-center hover:opacity-80 transition-colors"
            >
              <FaExternalLinkAlt className="mr-2" />
              Go to Flow
            </a>
          </div>
        </div>

        <div className="bg-base-100 rounded-lg shadow-md p-6">
          <h2 className="text-xl font-bold mb-4">Execution Flow</h2>
          <ExecutionDAG
            tasks={execution.task.map((task) => ({
              task_id: task.task_id,
              name: task.name,
              status: task.status,
              upstream_id: task.upstream_id || undefined,
              start_at: task.start_at || undefined,
              elapsed_time: task.elapsed_time || undefined,
            }))}
          />
        </div>

        <div className="bg-base-100 rounded-lg shadow-md p-6">
          <div className="space-y-4">
            <h2 className="text-xl font-bold">Tasks</h2>
            {execution.task?.map((task: any, index: number) => {
              const taskBorderStyle = getStatusBorderStyle(task.status);

              return (
                <details
                  key={index}
                  className={`bg-base-100 rounded-lg shadow-md ${taskBorderStyle}`}
                >
                  <summary className="p-4 cursor-pointer hover:bg-base-200 rounded-lg">
                    <div className="flex justify-between items-center">
                      <h3 className="text-lg font-semibold">{task.name}</h3>
                      <span
                        className={`text-sm font-semibold ${
                          task.status === "running"
                            ? "text-info"
                            : task.status === "completed"
                            ? "text-success"
                            : task.status === "scheduled"
                            ? "text-warning"
                            : "text-error"
                        }`}
                      >
                        {task.status}
                      </span>
                    </div>
                    <div className="text-sm text-base-content/60 mt-1">
                      <p>
                        Start at: {new Date(task.start_at).toLocaleString()}
                      </p>
                      <p>Elapsed time: {task.elapsed_time}</p>
                    </div>
                  </summary>

                  <div className="p-4 border-t">
                    {Array.isArray(task.figure_path) ? (
                      task.figure_path.map((path: string, i: number) => (
                        <div key={i} className="mt-4">
                          <h4 className="text-md font-semibold mb-2">
                            Figure {i + 1}
                          </h4>
                          <img
                            src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                              path
                            )}`}
                            alt={`Task Figure ${i + 1}`}
                            className="w-full h-auto max-h-[60vh] object-contain rounded border"
                          />
                        </div>
                      ))
                    ) : task.figure_path ? (
                      <div className="mt-4">
                        <h4 className="text-md font-semibold mb-2">Figure</h4>
                        <img
                          src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                            task.figure_path
                          )}`}
                          alt="Task Figure"
                          className="w-full h-auto max-h-[60vh] object-contain rounded border"
                        />
                      </div>
                    ) : null}

                    <div className="mt-4">
                      <h4 className="text-md font-semibold mb-2">
                        Input Parameters
                      </h4>
                      <div className="bg-base-200 p-2 rounded">
                        <JsonView
                          src={task.input_parameters}
                          theme="vscode"
                          collapsed={1}
                        />
                      </div>
                    </div>

                    <div className="mt-4">
                      <h4 className="text-md font-semibold mb-2">
                        Output Parameters
                      </h4>
                      <div className="bg-base-200 p-2 rounded">
                        <JsonView
                          src={task.output_parameters}
                          theme="vscode"
                          collapsed={2}
                        />
                      </div>
                    </div>
                  </div>
                </details>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
