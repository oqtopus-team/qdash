import type { InvestigationTarget } from "@/types/copilotChat";

/** Identifies one failure, so a second click resumes its chat instead of starting another. */
export function investigationKey(target: InvestigationTarget): string {
  return [target.executionId, target.taskId ?? "", target.taskName ?? "", target.qid ?? ""].join(
    "|",
  );
}

export function sameInvestigation(
  a: InvestigationTarget | null | undefined,
  b: InvestigationTarget,
): boolean {
  return Boolean(a) && investigationKey(a as InvestigationTarget) === investigationKey(b);
}

function taskLabel(target: InvestigationTarget): string | null {
  if (!target.taskName && !target.qid) return null;
  return [target.taskName, target.qid].filter(Boolean).join(" / ");
}

/** The session title shown in the chat list. */
export function investigationTitle(target: InvestigationTarget): string {
  const task = taskLabel(target);
  return task ? `Investigate ${task}` : `Investigate execution ${target.executionId}`;
}

/**
 * The message the user sees as their first turn. The API puts the logs, the
 * identifiers and the answering instructions in front of it, so it stays short.
 */
export function investigationPrompt(target: InvestigationTarget): string {
  const task = taskLabel(target);
  const subject = task
    ? `the failure of ${task} in execution ${target.executionId}`
    : `why execution ${target.executionId} failed`;
  return `Investigate ${subject}. Use the recorded logs and the QDash source to find the likely cause.`;
}

/** The target as the chat API's `investigation` field takes it. */
export function toInvestigationRequest(target: InvestigationTarget) {
  return {
    execution_id: target.executionId,
    ...(target.taskId ? { task_id: target.taskId } : {}),
    ...(target.taskName ? { task_name: target.taskName } : {}),
    ...(target.qid ? { qid: target.qid } : {}),
    ...(target.chipId ? { chip_id: target.chipId } : {}),
  };
}

/** Read an investigation back from a stored session context (`{ investigation: {...} }`). */
export function investigationFromStored(value: unknown): InvestigationTarget | null {
  if (!value || typeof value !== "object") return null;
  const raw = (value as { investigation?: unknown }).investigation;
  if (!raw || typeof raw !== "object") return null;
  const record = raw as Record<string, unknown>;
  if (typeof record.executionId !== "string" || !record.executionId) return null;
  const optional = (key: string) =>
    typeof record[key] === "string" ? (record[key] as string) : null;
  return {
    executionId: record.executionId,
    taskId: optional("taskId"),
    taskName: optional("taskName"),
    qid: optional("qid"),
    chipId: optional("chipId"),
  };
}

/** A failed task result as an investigation target; null unless it failed in a known execution. */
export function failedTaskInvestigation(
  result:
    | {
        status?: string | null;
        execution_id?: string | null;
        task_id?: string | null;
        task_name?: string | null;
        qid?: string | null;
        chip_id?: string | null;
      }
    | null
    | undefined,
): InvestigationTarget | null {
  if (!result || result.status !== "failed" || !result.execution_id) return null;
  return {
    executionId: result.execution_id,
    taskId: result.task_id ?? null,
    taskName: result.task_name ?? null,
    qid: result.qid ?? null,
    chipId: result.chip_id ?? null,
  };
}
