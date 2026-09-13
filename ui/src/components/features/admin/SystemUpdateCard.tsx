"use client";

import { useEffect, useState } from "react";
import { ArrowUpCircle, RefreshCw, ServerCog, ShieldCheck } from "lucide-react";

import {
  getGetSystemUpdateStatusQueryKey,
  useGetSystemUpdateOperation,
  useGetSystemUpdateStatus,
  useStartSystemUpdate,
} from "@/client/admin/admin";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useQueryClient } from "@tanstack/react-query";
import type { SystemUpdateState } from "@/schemas";

const OPERATION_STORAGE_KEY = "qdash-system-update-operation";
const ACTIVE_STATES: SystemUpdateState[] = ["queued", "running", "rolling_back"];

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "The system updater could not be reached.";
}

function stateBadgeClass(state: SystemUpdateState): string {
  if (state === "succeeded") return "badge-success";
  if (state === "failed") return "badge-error";
  if (state === "rolled_back") return "badge-warning";
  if (ACTIVE_STATES.includes(state)) return "badge-info";
  return "badge-ghost";
}

export function SystemUpdateCard() {
  const queryClient = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [operationId, setOperationId] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(OPERATION_STORAGE_KEY);
  });

  const statusQuery = useGetSystemUpdateStatus({
    query: {
      retry: 2,
      refetchInterval: operationId ? false : 60_000,
    },
  });
  const operationQuery = useGetSystemUpdateOperation(operationId ?? "", {
    query: {
      enabled: !!operationId,
      retry: true,
      refetchInterval: (query) => {
        const state = query.state.data?.data.state;
        return state === undefined || ACTIVE_STATES.includes(state) ? 2_000 : false;
      },
    },
  });
  const startMutation = useStartSystemUpdate({
    mutation: {
      onSuccess: (response) => {
        const nextOperationId = response.data.operation_id;
        window.localStorage.setItem(OPERATION_STORAGE_KEY, nextOperationId);
        setOperationId(nextOperationId);
        setConfirmOpen(false);
      },
    },
  });

  const updateStatus = statusQuery.data?.data;
  const operation = operationQuery.data?.data;

  useEffect(() => {
    if (
      !operationId &&
      updateStatus?.operation_id &&
      updateStatus.operation_state &&
      ACTIVE_STATES.includes(updateStatus.operation_state)
    ) {
      window.localStorage.setItem(OPERATION_STORAGE_KEY, updateStatus.operation_id);
      setOperationId(updateStatus.operation_id);
    }
  }, [operationId, updateStatus?.operation_id, updateStatus?.operation_state]);

  useEffect(() => {
    if (!operation || ACTIVE_STATES.includes(operation.state)) return;
    window.localStorage.removeItem(OPERATION_STORAGE_KEY);
    queryClient.invalidateQueries({ queryKey: getGetSystemUpdateStatusQueryKey() });
  }, [operation, queryClient]);

  const handleStart = () => {
    if (!updateStatus) return;
    startMutation.mutate({
      data: { expected_current_version: updateStatus.current_version },
    });
  };

  const handleDismissOperation = () => {
    window.localStorage.removeItem(OPERATION_STORAGE_KEY);
    setOperationId(null);
  };

  return (
    <div className="card bg-base-200 shadow-lg">
      <div className="card-body gap-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="card-title text-xl">
              <ServerCog className="h-5 w-5" />
              System Update
            </h2>
            <p className="mt-1 text-sm text-base-content/60">
              Install a release only when its manifest declares automatic migration support.
            </p>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => statusQuery.refetch()}
            disabled={statusQuery.isFetching || !!operationId}
          >
            <RefreshCw className={`h-4 w-4 ${statusQuery.isFetching ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>

        {statusQuery.isLoading ? (
          <div className="flex h-32 items-center justify-center">
            <span className="loading loading-spinner loading-md" />
          </div>
        ) : statusQuery.isError ? (
          <div role="alert" className="alert alert-error alert-soft">
            <span>{errorMessage(statusQuery.error)}</span>
          </div>
        ) : updateStatus ? (
          <>
            <div className="stats stats-vertical bg-base-100 sm:stats-horizontal">
              <div className="stat">
                <div className="stat-title">Current release</div>
                <div className="stat-value text-2xl font-mono">{updateStatus.current_version}</div>
                <div className="stat-desc font-mono">
                  {updateStatus.current_commit.slice(0, 12)}
                </div>
              </div>
              <div className="stat">
                <div className="stat-title">Latest stable</div>
                <div className="stat-value text-2xl font-mono">
                  {updateStatus.latest_version ?? "Unknown"}
                </div>
                <div className="stat-desc">
                  {updateStatus.update_available ? "Update available" : "No newer release"}
                </div>
              </div>
            </div>

            {updateStatus.dirty && (
              <div role="alert" className="alert alert-warning alert-soft">
                <span>The tracked working tree has changes. Commit or restore them first.</span>
              </div>
            )}

            {!updateStatus.enabled && (
              <div role="alert" className="alert alert-info alert-soft">
                <span>
                  The host updater is not running. On the QDash host, run{" "}
                  <code className="font-mono">
                    uv run --isolated --locked --no-dev qdash-updater start
                  </code>
                  , then restart the API container.
                </span>
              </div>
            )}

            {updateStatus.blocked_reason && updateStatus.enabled && !operation && (
              <div role="alert" className="alert alert-warning alert-soft">
                <span>{updateStatus.blocked_reason}</span>
              </div>
            )}

            {operation && (
              <div className="rounded-box border border-base-300 bg-base-100 p-4">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`badge ${stateBadgeClass(operation.state)}`}>
                      {operation.state.replace("_", " ")}
                    </span>
                    <span className="text-sm font-medium">{operation.message}</span>
                  </div>
                  <span className="text-sm tabular-nums text-base-content/60">
                    {operation.progress}%
                  </span>
                </div>
                <progress
                  className="progress progress-info mt-3 w-full"
                  value={operation.progress}
                  max={100}
                />
                <div className="mt-2 text-xs text-base-content/50">
                  {operation.source_version} → {operation.target_version} · {operation.stage}
                </div>
                {!ACTIVE_STATES.includes(operation.state) && (
                  <div className="mt-3 flex justify-end">
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={handleDismissOperation}
                    >
                      Dismiss
                    </button>
                  </div>
                )}
              </div>
            )}

            <div className="card-actions items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm text-base-content/60">
                <ShieldCheck className="h-4 w-4" />
                Admin only · application services restart during update
              </div>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => setConfirmOpen(true)}
                disabled={!updateStatus.can_update || !!operationId || startMutation.isPending}
              >
                <ArrowUpCircle className="h-4 w-4" />
                Update to {updateStatus.latest_version ?? "latest"}
              </button>
            </div>

            {startMutation.isError && (
              <div role="alert" className="alert alert-error alert-soft">
                <span>{errorMessage(startMutation.error)}</span>
              </div>
            )}
          </>
        ) : null}
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title={`Update QDash to ${updateStatus?.latest_version ?? "the latest release"}?`}
        description={
          <span>
            QDash application services will be unavailable while images are rebuilt. Running
            calibrations are checked again before the update starts.
          </span>
        }
        confirmLabel="Start update"
        onConfirm={handleStart}
        onOpenChange={setConfirmOpen}
        pending={startMutation.isPending}
      />
    </div>
  );
}
