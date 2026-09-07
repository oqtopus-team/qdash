"use client";

import { useState } from "react";

import { useRetryCalibrationGitHubSync } from "@/client/calibration/calibration";
import type { ManualParameterUpdateResponse } from "@/schemas";

export function CalibrationGitHubSyncNotice({
  result,
}: {
  result: Pick<ManualParameterUpdateResponse, "task_id" | "github_sync">;
}) {
  const [sync, setSync] = useState(result.github_sync);
  const retry = useRetryCalibrationGitHubSync();
  if (!sync || sync.status === "disabled") return null;
  if (sync.status === "synced") {
    return <p className="mt-2 text-xs text-success">GitHub synchronized.</p>;
  }
  return (
    <div className="alert alert-warning mt-3 text-sm" role="status">
      <span>
        Values are applied to the database and local YAML. GitHub synchronization failed.
        {retry.isError && " Retry failed. Please try again."}
      </span>
      <button
        className="btn btn-sm btn-outline"
        disabled={retry.isPending}
        onClick={() =>
          retry.mutate(
            { taskId: result.task_id },
            { onSuccess: (response) => setSync(response.data) },
          )
        }
      >
        {retry.isPending ? "Synchronizing…" : "Retry GitHub sync"}
      </button>
    </div>
  );
}
