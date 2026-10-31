"use client";

import { Bot } from "lucide-react";

import { useListEvaluations } from "@/client/evaluation/evaluation";
import { useGetTaskResult } from "@/client/task/task";
import type { TaskChatContext } from "@/types/copilotChat";

import { AskAiButton } from "./AskAiButton";
import { EvaluationCard } from "./EvaluationCard";

interface TaskResultEvaluationsProps {
  taskId: string;
  /** Pass all three when known; any left out make the section fetch the result to fill them. */
  chipId?: string | null;
  taskName?: string;
  qid?: string;
  executionId?: string;
  /** How this surface opens a chat about the result; default: the chat dock. */
  onChat?: () => void;
}

/**
 * The AI evaluations of one task result, newest first, with the "Ask AI"
 * entry to request another or chat about the result. A single result's
 * evaluation takes the same path, with the same choices (model only or via
 * Copilot, labeled examples, a question), and leaves the same record as a
 * bulk run from the chip page.
 */
export function TaskResultEvaluations({
  taskId,
  chipId: givenChipId,
  taskName: givenTaskName,
  qid: givenQid,
  executionId: givenExecutionId,
  onChat,
}: TaskResultEvaluationsProps) {
  const needsResult =
    !givenTaskName || !givenQid || givenChipId === undefined || givenExecutionId === undefined;
  const { data: resultResponse } = useGetTaskResult(taskId, {
    query: { enabled: !!taskId && needsResult, staleTime: 60_000 },
  });
  const taskName = givenTaskName ?? resultResponse?.data.task_name ?? "";
  const qid = givenQid ?? resultResponse?.data.qid ?? "";
  const chipId = givenChipId ?? resultResponse?.data.chip_id ?? null;
  const executionId = givenExecutionId ?? resultResponse?.data.execution_id ?? "";
  const chatContext: TaskChatContext | null =
    chipId && taskName && qid ? { taskName, chipId, qid, executionId, taskId } : null;
  const { data: response } = useListEvaluations(
    { task_id: taskId },
    {
      query: {
        enabled: !!taskId,
        refetchInterval: (query) =>
          query.state.data?.data.evaluations.some(
            (item) => item.status === "pending" || item.status === "running",
          )
            ? 5_000
            : false,
      },
    },
  );
  const evaluations = response?.data.evaluations ?? [];

  return (
    <section className="mb-6">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Bot className="h-4 w-4 text-primary" />
          AI evaluation
          {evaluations.length > 0 && (
            <span className="badge badge-ghost badge-sm">{evaluations.length}</span>
          )}
        </div>
        <AskAiButton
          taskId={taskId}
          chipId={chipId}
          taskName={taskName}
          qid={qid}
          chatContext={chatContext}
          onChat={onChat}
          variant="outline"
        />
      </div>
      {evaluations.length === 0 ? (
        <p className="text-sm text-base-content/50">
          No AI evaluation yet. Ask AI sends the figure and the task&apos;s reference to the
          calibration evaluation model and keeps the record here, or opens a chat about the result.
        </p>
      ) : (
        <div className="space-y-3">
          {evaluations.map((item) => (
            <EvaluationCard
              key={item.evaluation_id}
              item={item}
              showFigure={false}
              showTarget={false}
              showRunLink
            />
          ))}
        </div>
      )}
    </section>
  );
}
