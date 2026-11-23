"use client";

import { useEffect, useRef } from "react";

import { useGetExecution } from "@/client/execution/execution";
import { getProjectId } from "@/lib/auth/session";
import type { JourneyState } from "@/lib/firstCalibrationJourney";

import { journeyQueryKeys } from "./journeyQueryKeys";
import { useFirstCalibrationJourney } from "./useFirstCalibrationJourney";
import { useJourneyScope } from "./useFirstCalibrationProgress";

interface ViewedResult {
  task_id: string;
  execution_id: string;
  status: string;
}

interface PendingLeave {
  executionId: string;
  taskId: string;
  timer: ReturnType<typeof setTimeout>;
}

/**
 * Record that the user inspected a task result of the journey's run, once they are done with it:
 * when the result's view closes, shows another result, or leaves the page. Only a successful
 * result of that run counts; a result of any other execution, or one still running or failed,
 * leaves the journey where it is.
 *
 * While the result is open the journey stays on its result step, where the guide explains the
 * graph and fitted values; the guide records the same event itself when that explanation ends
 * (see `CoachmarkPlan.completion`). This hook covers a result the guide does not explain, such as
 * another completed task of the run. Whichever comes first counts; the other changes nothing.
 *
 * The result on screen may come from a cache filled in another project, and execution ids repeat
 * across projects. So the result only counts once the journey's execution, read in the current
 * user and project, lists that task as completed. A failed read never confirms it.
 */
export function useRecordJourneyResultView(result: ViewedResult | undefined | null): void {
  const { state, record } = useFirstCalibrationJourney();
  const scope = useJourneyScope();
  const executionId = state?.status === "active" ? state.executionId : null;
  const startedAt = state?.startedAt;
  const alreadyInspected = state?.inspectedTaskId != null;

  const taskId = result?.task_id;
  const resultExecutionId = result?.execution_id;
  const status = result?.status;
  const candidate =
    Boolean(taskId) &&
    executionId !== null &&
    !alreadyInspected &&
    resultExecutionId === executionId &&
    status === "completed";

  const { data: executionResponse } = useGetExecution(executionId ?? "", {
    query: {
      queryKey: journeyQueryKeys.execution(scope, executionId ?? ""),
      enabled: candidate && scope !== null,
      retry: false,
    },
  });
  const confirmed = Boolean(
    candidate &&
    executionResponse?.data?.task?.some(
      (task) => task.task_id === taskId && task.status === "completed",
    ),
  );

  // The journey as stored now, read when the view ends; it may have been paused, finished by the
  // guide or restarted while the result was open.
  const latestState = useRef<JourneyState | null>(state);
  useEffect(() => {
    latestState.current = state;
  });

  // Leaving is decided a tick later, so a remount of the same view (React's development double
  // mount, or a re-render that keeps the result) does not count as leaving it.
  const pendingLeave = useRef<PendingLeave | null>(null);

  useEffect(() => {
    if (!confirmed || !taskId || !executionId) return;
    const pending = pendingLeave.current;
    if (pending && pending.executionId === executionId && pending.taskId === taskId) {
      clearTimeout(pending.timer);
      pendingLeave.current = null;
    }
    // The project and journey the result was confirmed in; the event is written to them only.
    const projectId = getProjectId();
    return () => {
      const timer = setTimeout(() => {
        if (pendingLeave.current?.timer === timer) pendingLeave.current = null;
        const now = latestState.current;
        if (
          getProjectId() !== projectId ||
          now?.status !== "active" ||
          now.startedAt !== startedAt ||
          now.executionId !== executionId ||
          now.inspectedTaskId !== null
        ) {
          return;
        }
        record({ type: "resultInspected", executionId, taskId });
      }, 0);
      pendingLeave.current = { executionId, taskId, timer };
    };
  }, [confirmed, taskId, executionId, startedAt, record]);
}
