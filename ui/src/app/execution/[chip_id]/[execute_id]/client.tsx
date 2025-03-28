"use client";

import { useFetchExecutionByChipId } from "@/client/chip/chip";
import { FaExternalLinkAlt, FaDownload } from "react-icons/fa";
import JsonView from "react18-json-view";
import { ExecutionResponseDetail } from "@/schemas";
import ExecutionDAG from "./ExecutionDAG";
import { LoadingSpinner } from "@/app/components/LoadingSpinner";
import { TaskFigure } from "@/app/components/TaskFigure";

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
  } = useFetchExecutionByChipId(chip_id, execute_id, {
    query: {
      // Refresh every 5 seconds
      refetchInterval: 5000,
      // Keep polling even when the window is in the background
      refetchIntervalInBackground: true,
    },
  });

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

  if (isDetailLoading) {
    return (
      <div
        className="w-full px-4 py-6 min-h-screen"
        style={{ width: "calc(100vw - 20rem)" }}
      >
        <div className="space-y-6">
          {/* Header Skeleton with Loading Spinner */}
          <div className="flex justify-between items-center">
            <div className="h-10 w-64 bg-base-300 rounded animate-pulse"></div>
            <div className="flex space-x-4">
              <div className="h-10 w-36 bg-base-300 rounded animate-pulse"></div>
              <div className="h-10 w-36 bg-base-300 rounded animate-pulse"></div>
            </div>
          </div>

          {/* Loading Spinner */}
          <div className="flex justify-center items-center py-12">
            <LoadingSpinner />
          </div>

          {/* Tasks Skeleton */}
          <div className="bg-base-100 rounded-lg shadow-md p-6">
            <div className="h-8 w-32 bg-base-300 rounded animate-pulse mb-4"></div>
            <div className="space-y-4">
              {[1, 2].map((i) => (
                <div
                  key={i}
                  className="bg-base-100 rounded-lg shadow-md border-l-4 border-base-300"
                >
                  <div className="p-4">
                    <div className="flex justify-between items-center mb-2">
                      <div className="h-6 w-48 bg-base-300 rounded animate-pulse"></div>
                      <div className="h-6 w-24 bg-base-300 rounded animate-pulse"></div>
                    </div>
                    <div className="space-y-2">
                      <div className="h-4 w-36 bg-base-300 rounded animate-pulse"></div>
                      <div className="h-4 w-32 bg-base-300 rounded animate-pulse"></div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }
  if (isDetailError) return <div>Error loading execution details.</div>;
  if (!executionDetailData) return <div>No data found.</div>;

  const { data: execution } = executionDetailData as {
    data: ExecutionResponseDetail;
  };

  // Filter out tasks without task_id and ensure all required fields are present
  const validTasks = execution.task
    .filter((task) => task.task_id)
    .map((task) => ({
      task_id: task.task_id as string,
      name: task.name || "Unnamed Task",
      status: task.status || "unknown",
      upstream_id: task.upstream_id || undefined,
      start_at: task.start_at || undefined,
      elapsed_time: task.elapsed_time || undefined,
      figure_path: task.figure_path || undefined,
      input_parameters: task.input_parameters || undefined,
      output_parameters: task.output_parameters || undefined,
    }));

  return (
    <div className="w-full px-4 py-6" style={{ width: "calc(100vw - 20rem)" }}>
      <div className="space-y-6">
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
          <ExecutionDAG tasks={validTasks} />
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
                    <div className="space-y-6">
                      {/* Top Section - Raw Data Files and Figures */}
                      <div className="grid grid-cols-2 gap-6">
                        {/* Left Column - Raw Data Files */}
                        {task.raw_data_path &&
                          task.raw_data_path.length > 0 && (
                            <div>
                              <h4 className="text-md font-semibold mb-2">
                                Raw Data
                              </h4>
                              <div className="space-y-2">
                                {task.raw_data_path.map(
                                  (path: string, i: number) => (
                                    <div
                                      key={i}
                                      className="flex items-center justify-between bg-base-200 p-2 rounded"
                                    >
                                      <span className="text-sm truncate flex-1 mr-4">
                                        {path.split("/").pop()}
                                      </span>
                                      <button
                                        onClick={() => {
                                          // Create a link to download the file
                                          const link =
                                            document.createElement("a");
                                          // Ensure path starts with a slash
                                          const normalizedPath =
                                            path.startsWith("/")
                                              ? path
                                              : `/${path}`;
                                          const apiUrl =
                                            process.env.NEXT_PUBLIC_API_URL;
                                          link.href = `${apiUrl}/api/file/raw_data?path=${encodeURIComponent(
                                            normalizedPath,
                                          )}`;
                                          // Get just the filename for download
                                          const filename =
                                            path.split("/").pop() || "file";
                                          link.download = filename;
                                          document.body.appendChild(link);
                                          link.click();
                                          document.body.removeChild(link);
                                        }}
                                        className="btn btn-sm btn-primary"
                                      >
                                        <FaDownload className="mr-2" />
                                        Download
                                      </button>
                                    </div>
                                  ),
                                )}
                              </div>
                            </div>
                          )}

                        {/* Right Column - Figures */}
                        <div>
                          {Array.isArray(task.figure_path) ? (
                            task.figure_path.map((path: string, i: number) => (
                              <div key={i} className="mb-4">
                                <h4 className="text-md font-semibold mb-2">
                                  Figure {i + 1}
                                </h4>
                                <TaskFigure
                                  path={path}
                                  qid={task.qid || ""}
                                  className="w-full h-auto max-h-[60vh] object-contain rounded border"
                                />
                              </div>
                            ))
                          ) : task.figure_path ? (
                            <div>
                              <h4 className="text-md font-semibold mb-2">
                                Figure
                              </h4>
                              <TaskFigure
                                path={task.figure_path}
                                qid={task.qid || ""}
                                className="w-full h-auto max-h-[60vh] object-contain rounded border"
                              />
                            </div>
                          ) : null}
                        </div>
                      </div>

                      {/* Bottom Section - Parameters */}
                      <div className="grid grid-cols-2 gap-6 border-t pt-4">
                        {/* Left Column - Input Parameters */}
                        <details className="bg-base-200 rounded" open={false}>
                          <summary className="p-2 cursor-pointer hover:bg-base-300">
                            <h4 className="text-md font-semibold inline-block">
                              Input Parameters
                            </h4>
                          </summary>
                          <div className="px-2 pb-2">
                            <JsonView
                              src={task.input_parameters}
                              theme="vscode"
                              collapsed={3}
                              style={{ fontSize: "0.875rem" }}
                            />
                          </div>
                        </details>

                        {/* Right Column - Output Parameters */}
                        <details className="bg-base-200 rounded" open={false}>
                          <summary className="p-2 cursor-pointer hover:bg-base-300">
                            <h4 className="text-md font-semibold inline-block">
                              Output Parameters
                            </h4>
                          </summary>
                          <div className="px-2 pb-2">
                            <JsonView
                              src={task.output_parameters}
                              theme="vscode"
                              collapsed={3}
                              style={{ fontSize: "0.875rem" }}
                            />
                          </div>
                        </details>
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
