"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { ExternalLink, Lock, Play, RefreshCw, RotateCcw } from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";

import type { ExecutionResponseDetail, TaskInfo } from "@/schemas";

import { getChipCoupling, getChipQubit, useListChips } from "@/client/chip/chip";
import { useGetExecution, useGetExecutionLockStatus } from "@/client/execution/execution";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { ExecutionTaskProgress } from "@/components/features/execution/ExecutionTaskProgress";
import { ParametersTable } from "@/components/features/metrics/ParametersTable";
import { useToast } from "@/components/ui/Toast";
import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";
import { formatTaskParameter, parseTaskParameter } from "@/lib/utils/task-parameters";

interface TaskWorkbenchProps {
  task: TaskInfo;
  backend: string;
}

function badgeClass(status?: string | null) {
  if (status === "completed") return "badge-success";
  if (status === "failed") return "badge-error";
  if (status === "cancelled") return "badge-neutral";
  if (status === "running") return "badge-info";
  return "badge-warning";
}

export function TaskWorkbench({ task, backend }: TaskWorkbenchProps) {
  const toast = useToast();
  const { data: chipsData } = useListChips();
  const chips = chipsData?.data?.chips ?? [];
  const defaultChipId = chips[0]?.chip_id ?? "";

  const [chipIdQuery, setChipIdQuery] = useQueryState("chip", parseAsString);
  const [targetQuery, setTargetQuery] = useQueryState("target", parseAsString);
  const [executionIdQuery, setExecutionIdQuery] = useQueryState("execution", parseAsString);
  const [submittedChipIdQuery, setSubmittedChipIdQuery] = useQueryState(
    "executionChip",
    parseAsString,
  );
  const [submittedTargetQuery, setSubmittedTargetQuery] = useQueryState(
    "executionTarget",
    parseAsString,
  );
  const chipId = chipIdQuery ?? "";
  const target = targetQuery ?? "";
  const executionId = executionIdQuery ?? "";
  const submittedChipId = submittedChipIdQuery ?? "";
  const submittedTarget = submittedTargetQuery ?? "";
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  const [runValues, setRunValues] = useState<Record<string, string>>({});
  const [reconfigure, setReconfigure] = useState(false);
  const [persistOutputParameters, setPersistOutputParameters] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isReloadingInputs, setIsReloadingInputs] = useState(false);
  const previousTask = useRef(`${backend}:${task.name}`);

  const { data: lockStatus, isLoading: isLockStatusLoading } = useGetExecutionLockStatus({
    query: {
      refetchInterval: 5000,
    },
  });
  const isExecutionLocked = lockStatus?.data.lock ?? false;

  useEffect(() => {
    if (!chipIdQuery && defaultChipId) setChipIdQuery(defaultChipId);
  }, [chipIdQuery, defaultChipId, setChipIdQuery]);

  useEffect(() => {
    setRunValues(
      Object.fromEntries(
        Object.entries(task.run_parameters ?? {}).map(([name, parameter]) => [
          name,
          formatTaskParameter(parameter.value),
        ]),
      ),
    );
    setReconfigure(false);
    setPersistOutputParameters(false);
    const taskKey = `${backend}:${task.name}`;
    if (previousTask.current !== taskKey) {
      setTargetQuery(null);
      setExecutionIdQuery(null);
      setSubmittedChipIdQuery(null);
      setSubmittedTargetQuery(null);
      previousTask.current = taskKey;
    }
  }, [
    backend,
    setExecutionIdQuery,
    setSubmittedChipIdQuery,
    setSubmittedTargetQuery,
    setTargetQuery,
    task,
  ]);

  useEffect(() => {
    setInputValues(
      Object.fromEntries(Object.keys(task.input_parameters ?? {}).map((name) => [name, ""])),
    );
  }, [task.input_parameters]);

  const {
    data: executionResponse,
    error: executionQueryError,
    isError: executionError,
  } = useGetExecution(executionId, {
    query: {
      enabled: executionId.length > 0,
      refetchInterval: (query) => {
        const status = (query.state.data?.data as ExecutionResponseDetail | undefined)?.status;
        return status === "completed" || status === "failed" || status === "cancelled"
          ? false
          : 2000;
      },
      refetchIntervalInBackground: true,
    },
  });
  const isExecutionPendingCreation =
    (executionQueryError as { response?: { status?: number } } | null)?.response?.status === 404;

  const execution = executionResponse?.data as ExecutionResponseDetail | undefined;
  const isExecutionActive =
    isStarting ||
    (executionId.length > 0 &&
      (!execution || ["running", "scheduled", "pending"].includes(execution.status)));
  const resultTasks = useMemo(
    () =>
      (execution?.task ?? []).filter(
        (result) =>
          result.name === task.name && (!submittedTarget || result.qid === submittedTarget),
      ),
    [execution?.task, submittedTarget, task.name],
  );
  const resultTask = resultTasks[resultTasks.length - 1];
  const figures: string[] = Array.isArray(resultTask?.figure_path)
    ? resultTask.figure_path
    : resultTask?.figure_path
      ? [resultTask.figure_path]
      : [];
  const jsonFigures: string[] = Array.isArray(resultTask?.json_figure_path)
    ? resultTask.json_figure_path
    : resultTask?.json_figure_path
      ? [resultTask.json_figure_path]
      : [];

  const handleRun = async () => {
    if (!chipId || !target.trim()) return;
    const requestedTarget = target.trim();
    setIsStarting(true);
    try {
      const runParameterOverrides = Object.fromEntries(
        Object.entries(runValues)
          .filter(([, value]) => value.trim() !== "")
          .map(([name, value]) => [
            name,
            parseTaskParameter(value, task.run_parameters?.[name]?.value_type),
          ]),
      );
      const inputParameterOverrides = Object.fromEntries(
        Object.entries(inputValues)
          .filter(([, value]) => value.trim() !== "")
          .map(([name, value]) => [
            name,
            parseTaskParameter(value, task.input_parameters?.[name]?.value_type ?? "float"),
          ]),
      );
      const response = await AXIOS_INSTANCE.post(`/tasks/${task.name}/execute`, {
        chip_id: chipId,
        qid: requestedTarget,
        backend_name: backend,
        input_parameter_overrides: inputParameterOverrides,
        run_parameter_overrides: runParameterOverrides,
        reconfigure,
        persist_output_parameters: persistOutputParameters,
        update_params: false,
      });
      setExecutionIdQuery(response.data.execution_id);
      setSubmittedChipIdQuery(chipId);
      setSubmittedTargetQuery(requestedTarget);
      toast.success(`${task.name} started`);
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;
      toast.error(detail ?? (error instanceof Error ? error.message : "Failed to start task"));
    } finally {
      setIsStarting(false);
    }
  };

  const handleReloadInputParameters = async () => {
    if (!chipId || !target.trim()) return;
    setIsReloadingInputs(true);
    try {
      const qid = target.trim();
      const isCoupling = task.task_type === "coupling" || qid.includes("-");
      let calibrationSources: Record<string, Record<string, unknown>>;
      if (isCoupling) {
        const [controlQid, targetQid] = qid.split("-", 2);
        if (!controlQid || !targetQid) throw new Error("Coupling target must be control-target");
        const [controlResponse, targetResponse, couplingResponse] = await Promise.all([
          getChipQubit(chipId, controlQid),
          getChipQubit(chipId, targetQid),
          getChipCoupling(chipId, qid),
        ]);
        calibrationSources = {
          control: controlResponse.data.data ?? {},
          target: targetResponse.data.data ?? {},
          coupling: couplingResponse.data.data ?? {},
          self: couplingResponse.data.data ?? {},
        };
      } else {
        const response = await getChipQubit(chipId, qid);
        calibrationSources = { self: response.data.data ?? {} };
      }
      let loadedCount = 0;
      const loadedValues = Object.fromEntries(
        Object.entries(task.input_parameters ?? {}).map(([name, parameter]) => {
          const role = String(parameter.qid_role || "self");
          const lookupName = String(parameter.parameter_name || name);
          const primarySource = calibrationSources[role] ?? calibrationSources.self ?? {};
          const couplingFallback = calibrationSources.coupling ?? {};
          const resolution = String(parameter.resolution ?? "database_required");
          let stored: unknown;
          if (resolution !== "default_only") {
            stored = Object.prototype.hasOwnProperty.call(primarySource, lookupName)
              ? primarySource[lookupName]
              : couplingFallback[lookupName];
          }
          let value =
            stored && typeof stored === "object" && "value" in stored
              ? (stored as { value?: unknown }).value
              : stored;
          if (value === null || value === undefined) value = parameter.default_value;
          if (value === null || value === undefined) return [name, ""];
          loadedCount += 1;
          return [name, Array.isArray(value) ? JSON.stringify(value) : String(value)];
        }),
      );
      setInputValues(loadedValues);
      if (loadedCount > 0) {
        toast.success(
          `Loaded ${loadedCount} current input parameter${loadedCount === 1 ? "" : "s"}`,
        );
      } else {
        toast.error("No current input parameter values were found for this target");
      }
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;
      toast.error(detail ?? "Failed to load current input parameters");
    } finally {
      setIsReloadingInputs(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-base-200 p-3 sm:p-4">
      <div className="w-full space-y-4">
        <div className="flex min-w-0 flex-col justify-between gap-3 sm:flex-row sm:items-start">
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <h1 className="min-w-0 break-words text-2xl font-bold">{task.name}</h1>
              <span className="badge badge-outline max-w-full truncate">
                {task.task_type || "task"}
              </span>
            </div>
            <p className="mt-1 max-w-3xl break-words text-sm text-base-content/60">
              {task.description ||
                "Run this calibration task directly without creating a workflow."}
            </p>
          </div>
        </div>

        <div className="grid items-start gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
          <section className="min-w-0 rounded-box border border-base-300 bg-base-100 p-4 shadow-sm">
            <div className="flex min-w-0 flex-col gap-4">
              <h2 className="text-lg font-semibold">Setup</h2>
              <div className="grid gap-3">
                <label className="form-control min-w-0">
                  <span className="label-text mb-1">Chip</span>
                  <select
                    className="select select-bordered w-full"
                    value={chipId}
                    onChange={(event) => setChipIdQuery(event.target.value)}
                  >
                    <option value="" disabled>
                      Select a chip
                    </option>
                    {chips.map((chip) => (
                      <option key={chip.chip_id} value={chip.chip_id}>
                        {chip.chip_id}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-control min-w-0">
                  <span className="label-text mb-1">Qubit or coupling</span>
                  <input
                    className="input input-bordered w-full"
                    value={target}
                    onChange={(event) => setTargetQuery(event.target.value)}
                    disabled={isExecutionActive}
                    placeholder="e.g. 0 or 0-1"
                  />
                </label>
              </div>

              {Object.keys(task.input_parameters ?? {}).length > 0 && (
                <div>
                  <div className="mb-2 flex min-w-0 items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h3 className="text-sm font-semibold">Input parameter overrides</h3>
                      <p className="break-words text-xs text-base-content/50">
                        Leave blank to use the current calibration value.
                      </p>
                    </div>
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs shrink-0"
                      onClick={handleReloadInputParameters}
                      disabled={!chipId || !target.trim() || isReloadingInputs}
                      title="Reload current values from the calibration database"
                    >
                      {isReloadingInputs ? (
                        <span className="loading loading-spinner loading-xs" />
                      ) : (
                        <RefreshCw size={13} />
                      )}
                      Reload
                    </button>
                  </div>
                  <div className="grid max-h-64 gap-3 overflow-y-auto rounded-lg border border-base-300 p-3">
                    {Object.entries(task.input_parameters ?? {}).map(([name, parameter]) => (
                      <label key={name} className="form-control min-w-0">
                        <span className="label-text mb-1 flex min-w-0 items-start justify-between gap-2">
                          <span className="min-w-0 break-words">{name}</span>
                          <span className="max-w-[45%] shrink-0 break-all text-right text-base-content/40">
                            {String(parameter.unit ?? "")}
                          </span>
                        </span>
                        <input
                          className="input input-sm input-bordered font-mono"
                          value={inputValues[name] ?? ""}
                          onChange={(event) =>
                            setInputValues((current) => ({
                              ...current,
                              [name]: event.target.value,
                            }))
                          }
                          placeholder="Use current value"
                        />
                        {Boolean(parameter.description) && (
                          <span className="mt-1 break-words text-xs text-base-content/45">
                            {String(parameter.description)}
                          </span>
                        )}
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {Object.keys(task.run_parameters ?? {}).length > 0 && (
                <div>
                  <h3 className="mb-2 text-sm font-semibold">Run parameters</h3>
                  <div className="grid max-h-80 gap-3 overflow-y-auto rounded-lg border border-base-300 p-3">
                    {Object.entries(task.run_parameters ?? {}).map(([name, parameter]) => (
                      <label key={name} className="form-control min-w-0">
                        <span className="label-text mb-1 flex min-w-0 items-start justify-between gap-2">
                          <span className="min-w-0 break-words">{name}</span>
                          <span className="max-w-[45%] shrink-0 break-all text-right text-base-content/40">
                            {String(parameter.unit ?? "")}
                          </span>
                        </span>
                        <input
                          className="input input-sm input-bordered font-mono"
                          value={runValues[name] ?? ""}
                          onChange={(event) =>
                            setRunValues((current) => ({ ...current, [name]: event.target.value }))
                          }
                        />
                        {Boolean(parameter.description) && (
                          <span className="mt-1 break-words text-xs text-base-content/45">
                            {String(parameter.description)}
                          </span>
                        )}
                      </label>
                    ))}
                  </div>
                </div>
              )}

              <label className="label min-w-0 cursor-pointer items-start justify-start gap-3 whitespace-normal">
                <input
                  type="checkbox"
                  className="toggle toggle-sm"
                  checked={reconfigure}
                  onChange={(event) => setReconfigure(event.target.checked)}
                />
                <span className="min-w-0 break-words">
                  <span className="block break-words text-sm font-medium">
                    Reconfigure hardware first
                  </span>
                  <span className="block break-words text-xs text-base-content/50">
                    Apply the current calibration configuration before running the task.
                  </span>
                </span>
              </label>

              <label className="label min-w-0 cursor-pointer items-start justify-start gap-3 whitespace-normal">
                <input
                  type="checkbox"
                  className="toggle toggle-sm toggle-success mt-0.5 shrink-0"
                  checked={persistOutputParameters}
                  onChange={(event) => setPersistOutputParameters(event.target.checked)}
                />
                <span className="min-w-0 break-words">
                  <span className="block break-words text-sm font-medium">
                    Save calibrated outputs to DB
                  </span>
                  <span className="block break-words text-xs text-base-content/50">
                    Store this run&apos;s output parameters as the current calibration values.
                  </span>
                </span>
              </label>

              {persistOutputParameters && (
                <div className="alert alert-warning py-2 text-xs">
                  This run can change the calibration values used by later tasks.
                </div>
              )}

              {isExecutionLocked && (
                <div className="alert alert-warning py-2 text-xs">
                  Another calibration execution is running. Wait for it to finish before starting
                  this task.
                </div>
              )}

              <button
                className={`btn ${isExecutionLocked ? "btn-disabled" : "btn-primary"}`}
                onClick={handleRun}
                disabled={
                  isStarting ||
                  isLockStatusLoading ||
                  isExecutionLocked ||
                  isExecutionActive ||
                  !task.enabled ||
                  !chipId ||
                  !target.trim()
                }
                title={
                  isExecutionLocked
                    ? "Execution locked - another calibration is running"
                    : "Run task"
                }
              >
                {isStarting ? (
                  <span className="loading loading-spinner loading-sm" />
                ) : isExecutionLocked ? (
                  <Lock size={17} />
                ) : (
                  <Play size={17} />
                )}
                {isExecutionLocked ? "Locked" : "Run task"}
              </button>
            </div>
          </section>

          <section className="min-h-[38rem] min-w-0 rounded-box border border-base-300 bg-base-100 p-4 shadow-sm sm:p-5">
            <div className="flex min-h-[34rem] min-w-0 flex-col gap-4">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold">Results</h2>
                {execution && (
                  <span className={`badge ${badgeClass(execution.status)}`}>
                    {execution.status}
                  </span>
                )}
              </div>

              {!executionId ? (
                <div className="flex flex-1 flex-col items-center justify-center text-center text-base-content/40">
                  <Play className="mb-3 h-12 w-12 opacity-25" />
                  <p className="font-medium">No execution yet</p>
                  <p className="mt-1 text-sm">Configure the target and run parameters to start.</p>
                </div>
              ) : executionError && !isExecutionPendingCreation ? (
                <div className="alert alert-error">Failed to load the execution result.</div>
              ) : !execution ? (
                <div className="flex flex-1 items-center justify-center gap-3">
                  <span className="loading loading-spinner loading-md" />
                  <span>
                    {isExecutionPendingCreation
                      ? "Waiting for the worker to create the execution…"
                      : "Starting execution…"}
                  </span>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-2 rounded-lg bg-base-200 p-3 text-sm sm:grid-cols-4">
                    <div className="min-w-0">
                      <div className="text-xs text-base-content/45">Target</div>
                      <div className="truncate font-mono font-medium" title={submittedTarget}>
                        {submittedTarget}
                      </div>
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs text-base-content/45">Task</div>
                      <div className="truncate font-medium">{task.name}</div>
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs text-base-content/45">Status</div>
                      <div className="truncate font-medium">
                        {resultTask?.status || execution.status}
                      </div>
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs text-base-content/45">Duration</div>
                      <div className="truncate font-medium">
                        {resultTask?.elapsed_time || execution.elapsed_time || "-"}
                      </div>
                    </div>
                  </div>

                  {(execution.status === "running" ||
                    execution.status === "scheduled" ||
                    execution.status === "pending") && (
                    <>
                      <ExecutionTaskProgress status={resultTask?.status} note={resultTask?.note} />
                      {!resultTask?.note?.progress && (
                        <progress className="progress progress-primary w-full" />
                      )}
                    </>
                  )}

                  <div className="flex h-56 items-center justify-start gap-3 overflow-x-auto rounded-lg bg-base-200/60 p-3">
                    {figures.length > 0 ? (
                      figures.map((figure, index) => (
                        <TaskFigure
                          key={`${figure}-${index}`}
                          path={figure}
                          jsonFigurePath={jsonFigures[index]}
                          qid={submittedTarget}
                          className="h-full w-auto shrink-0 rounded object-contain"
                        />
                      ))
                    ) : resultTask?.task_id ? (
                      <TaskFigure
                        taskId={resultTask.task_id}
                        qid={submittedTarget}
                        className="h-full w-auto shrink-0 rounded object-contain"
                      />
                    ) : (
                      <span className="flex w-full justify-center text-sm text-base-content/40">
                        Waiting for a result figure…
                      </span>
                    )}
                  </div>

                  {resultTask?.input_parameters &&
                    Object.keys(resultTask.input_parameters).length > 0 && (
                      <ParametersTable
                        title="Input Parameters"
                        parameters={resultTask.input_parameters}
                      />
                    )}
                  {resultTask?.output_parameters &&
                    Object.keys(resultTask.output_parameters).length > 0 && (
                      <ParametersTable
                        title="Output Parameters"
                        parameters={resultTask.output_parameters}
                      />
                    )}
                  {resultTask?.run_parameters &&
                    Object.keys(resultTask.run_parameters).length > 0 && (
                      <ParametersTable
                        title="Run Parameters"
                        parameters={resultTask.run_parameters}
                      />
                    )}

                  <div className="flex flex-wrap justify-end gap-2">
                    <button
                      className="btn btn-sm btn-ghost"
                      onClick={() => {
                        setExecutionIdQuery(null);
                        setSubmittedChipIdQuery(null);
                        setSubmittedTargetQuery(null);
                      }}
                    >
                      <RotateCcw size={15} />
                      Adjust and run again
                    </button>
                    <Link
                      className="btn btn-sm btn-outline"
                      href={`/execution/${encodeURIComponent(submittedChipId)}/${encodeURIComponent(executionId)}`}
                    >
                      <ExternalLink size={15} />
                      Full execution
                    </Link>
                    {resultTask?.task_id && (
                      <Link
                        className="btn btn-sm btn-primary"
                        href={`/task-results/${resultTask.task_id}`}
                      >
                        Task result
                      </Link>
                    )}
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
