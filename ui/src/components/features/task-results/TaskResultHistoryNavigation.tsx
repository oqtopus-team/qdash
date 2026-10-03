"use client";

import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";

import {
  useGetCouplingTaskHistory,
  useGetQubitTaskHistory,
} from "@/client/task-result/task-result";
import type { TaskResult } from "@/schemas";

type TaskResultHistoryNavigationProps = {
  taskId: string;
  taskName: string;
  chipId?: string;
  qid: string;
};

function resultTimestamp(result: TaskResult) {
  const timestamp = result.end_at ?? result.start_at;
  return timestamp ? new Date(timestamp).getTime() : 0;
}

export function TaskResultHistoryNavigation({
  taskId,
  taskName,
  chipId,
  qid,
}: TaskResultHistoryNavigationProps) {
  const router = useRouter();
  const isCoupling = qid.includes("-");
  const canLoadHistory = Boolean(chipId && taskName && qid);
  const params = { chip_id: chipId ?? "", task: taskName };

  const qubitHistory = useGetQubitTaskHistory(qid, params, {
    query: {
      enabled: canLoadHistory && !isCoupling,
      staleTime: 30_000,
    },
  });
  const couplingHistory = useGetCouplingTaskHistory(qid, params, {
    query: {
      enabled: canLoadHistory && isCoupling,
      staleTime: 30_000,
    },
  });

  const activeHistory = isCoupling ? couplingHistory : qubitHistory;
  const historyEntries = Object.entries(activeHistory.data?.data.data ?? {}).sort(
    ([, left], [, right]) => resultTimestamp(right) - resultTimestamp(left),
  );
  const currentIndex = historyEntries.findIndex(([historyTaskId]) => historyTaskId === taskId);
  const nextTaskId = currentIndex > 0 ? historyEntries[currentIndex - 1]?.[0] : undefined;
  const previousTaskId =
    currentIndex >= 0 && currentIndex < historyEntries.length - 1
      ? historyEntries[currentIndex + 1]?.[0]
      : undefined;
  const isLoading = activeHistory.isLoading;

  return (
    <div className="join" aria-label="Task result history navigation">
      <button
        type="button"
        className="btn btn-sm btn-outline join-item gap-1"
        disabled={!previousTaskId || isLoading}
        onClick={() =>
          previousTaskId && router.push(`/task-results/${encodeURIComponent(previousTaskId)}`)
        }
        aria-label="Previous result"
        title="Previous result for the same task and target"
      >
        <ChevronLeft className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Previous</span>
      </button>
      <button
        type="button"
        className="btn btn-sm btn-outline join-item gap-1"
        disabled={!nextTaskId || isLoading}
        onClick={() => nextTaskId && router.push(`/task-results/${encodeURIComponent(nextTaskId)}`)}
        aria-label="Next result"
        title="Next result for the same task and target"
      >
        <span className="hidden sm:inline">Next</span>
        <ChevronRight className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
