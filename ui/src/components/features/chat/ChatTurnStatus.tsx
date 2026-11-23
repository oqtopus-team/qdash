"use client";

import { twMerge } from "tailwind-merge";
import type { SessionRun } from "@/contexts/CopilotChatSessionContext";
import { useCopilotChatSessionContext } from "@/contexts/CopilotChatSessionContext";
import {
  currentActivity,
  formatDuration,
  QUIET_AFTER_MS,
  useNow,
} from "@/components/features/chat/ChatTrace";
import { stepTitle } from "@/components/features/chat/ToolStepDetails";
import type {
  ChatMessage,
  CopilotBlocksResult,
  DetachedTurn,
  TraceStep,
  TurnActivitySnapshot,
} from "@/types/copilotChat";

/** What a chat's turn is doing, as the chat knows it from the turn's own events. */
export interface ChatStatus {
  kind:
    | "working"
    | "waiting_expert"
    | "waiting_execution"
    | "reconnecting"
    | "restoring"
    | "other_project"
    | "approval"
    | "question"
    | "edit"
    | "stopped"
    | "interrupted"
    | "in_progress"
    | "failed"
    | "answered";
  label: string;
  tone: "info" | "warning" | "neutral" | "success" | "error";
  /** When the turn last sent something; shown for a quiet or unwatched turn. */
  lastUpdateAt?: number | null;
  /** What the chat last saw an unwatched turn do. */
  lastActivity?: string | null;
  /** The turn is not streamed now: what is shown is the last state the chat knew. */
  stale?: boolean;
}

const WAIT_EXPERT = "qdash_wait_agent_intervention";
const WAIT_EXECUTION = new Set(["qdash_wait_execution", "qdash_wait_agent_action"]);

function runningTools(steps: TraceStep[]) {
  return steps.filter(
    (s): s is Extract<TraceStep, { kind: "tool" }> => s.kind === "tool" && s.status === "running",
  );
}

/** The phrase for a stored activity, as the live trace would show it. */
function activityTitle(activity: TurnActivitySnapshot | null | undefined): string | null {
  if (!activity) return null;
  if (!activity.tool) return activity.label;
  const title = stepTitle({
    kind: "tool",
    id: "",
    tool: activity.tool,
    label: activity.label,
    status: "running",
    startedAt: 0,
  });
  return title === activity.label ? `Running ${activity.label}` : title;
}

function lastAnswer(messages: ChatMessage[]): ChatMessage | undefined {
  let i = messages.length - 1;
  // Steers the answer read before it stopped follow it.
  while (i >= 0 && messages[i].role === "user" && messages[i].steer) i--;
  return messages[i];
}

function settledStatus(messages: ChatMessage[]): ChatStatus | null {
  const last = lastAnswer(messages);
  if (!last || last.role !== "assistant") return null;
  if (last.content.startsWith("Error: ")) return { kind: "failed", label: "Failed", tone: "error" };
  let payload: CopilotBlocksResult | null = null;
  try {
    payload = JSON.parse(last.content) as CopilotBlocksResult;
  } catch {
    payload = null;
  }
  if (payload?.stopped) return { kind: "stopped", label: "Stopped", tone: "neutral" };
  if (payload?.interrupted) return { kind: "interrupted", label: "Interrupted", tone: "neutral" };
  // Saved by the server while the turn ran, and no stream of it is followed here.
  if (payload?.in_progress) {
    return { kind: "in_progress", label: "Answer in progress", tone: "info", stale: true };
  }
  const types = new Set((payload?.blocks ?? []).map((b) => b.type));
  if (types.has("approval")) {
    return { kind: "approval", label: "Waiting for your approval", tone: "warning" };
  }
  if (types.has("ask"))
    return { kind: "question", label: "Waiting for your answer", tone: "warning" };
  if (types.has("edit")) return { kind: "edit", label: "Proposed a change", tone: "info" };
  return { kind: "answered", label: "Answered", tone: "success" };
}

/**
 * The chat's status from what it knows for certain: the live turn's events and its
 * connection, a turn this tab started that no stream follows now, or else how the last
 * saved answer ended. A quiet stream is never taken for progress or for an end.
 */
export function chatStatus({
  run,
  detached,
  messages,
}: {
  run?: SessionRun | null;
  detached?: DetachedTurn | null;
  messages: ChatMessage[];
}): ChatStatus | null {
  if (run) {
    const lastUpdateAt = run.connection?.lastUpdateAt ?? null;
    if (run.connection?.state === "reconnecting") {
      return { kind: "reconnecting", label: "Reconnecting", tone: "warning", lastUpdateAt };
    }
    const running = runningTools(run.turn.steps);
    const waiting = running[running.length - 1];
    if (waiting?.tool === WAIT_EXPERT) {
      return {
        kind: "waiting_expert",
        label: "Waiting for the expert's answer",
        tone: "info",
        lastUpdateAt,
      };
    }
    if (waiting && WAIT_EXECUTION.has(waiting.tool)) {
      return { kind: "waiting_execution", label: stepTitle(waiting), tone: "info", lastUpdateAt };
    }
    return {
      kind: "working",
      label: currentActivity(run.turn.steps, run.statusMessage) ?? "Working",
      tone: "info",
      lastUpdateAt,
    };
  }
  if (detached) {
    const base = {
      lastUpdateAt: detached.lastUpdateAt ?? detached.startedAt,
      lastActivity: activityTitle(detached.activity),
      stale: true,
    };
    return detached.reason === "other_project"
      ? { kind: "other_project", label: "Running in another project", tone: "neutral", ...base }
      : {
          kind: "restoring",
          label: "Reconnecting to the running answer",
          tone: "warning",
          ...base,
        };
  }
  return settledStatus(messages);
}

const TONE_CLASS: Record<ChatStatus["tone"], string> = {
  info: "status-info",
  warning: "status-warning",
  neutral: "status-neutral",
  success: "status-success",
  error: "status-error",
};

/** Whether the status describes a turn that has not ended (or may not have). */
function isOngoing(status: ChatStatus | null): boolean {
  return (
    status !== null &&
    [
      "working",
      "waiting_expert",
      "waiting_execution",
      "reconnecting",
      "restoring",
      "other_project",
    ].includes(status.kind)
  );
}

/**
 * One line saying what the chat's turn is doing: a status dot with its label, what an
 * unwatched turn was last seen doing, and when the turn last sent something. The label is
 * the live region; the ticking time is not announced.
 */
export function ChatStatusLine({
  status,
  className,
}: {
  status: ChatStatus | null;
  className?: string;
}) {
  const ongoing = isOngoing(status);
  const now = useNow(ongoing);
  if (!status) return null;
  const silent = status.lastUpdateAt != null ? now - status.lastUpdateAt : null;
  const showTime =
    silent !== null && (status.stale || status.kind === "reconnecting" || silent >= QUIET_AFTER_MS);
  return (
    <div
      className={twMerge(
        "flex min-w-0 items-center gap-1.5 text-xs text-base-content/60",
        className,
      )}
      data-testid="chat-status"
      data-kind={status.kind}
    >
      <span className={`status status-xs shrink-0 ${TONE_CLASS[status.tone]}`} aria-hidden="true" />
      <span role="status" className="truncate">
        {status.label}
        {status.lastActivity ? ` · last seen: ${status.lastActivity}` : ""}
      </span>
      {showTime && (
        <span className="shrink-0 tabular-nums" aria-hidden="true">
          · {status.stale ? "last known update" : "last update"} {formatDuration(silent)} ago
        </span>
      )}
    </div>
  );
}

/** The status of one chat (the active one by default), from the chat sessions. */
export function useChatStatus(sessionId?: string | null): ChatStatus | null {
  const { activeSession, sessions, runs, detachedTurns } = useCopilotChatSessionContext();
  const session =
    sessionId === undefined ? activeSession : (sessions.find((s) => s.id === sessionId) ?? null);
  if (!session) return null;
  return chatStatus({
    run: runs[session.id],
    detached: detachedTurns?.[session.id],
    messages: session.messages,
  });
}

/**
 * Where the live answer would be, for a turn of this tab no stream follows now: what the
 * chat last knew of it, marked as such, and what happens next.
 */
export function DetachedTurnRow({ turn }: { turn: DetachedTurn }) {
  const status = chatStatus({ detached: turn, messages: [] });
  return (
    <div className="rounded-[var(--radius-box)] border border-base-300 bg-base-200/40 px-3 py-2.5">
      <ChatStatusLine status={status} />
      <p className="mt-1 text-xs text-base-content/60">
        {turn.reason === "other_project"
          ? "This answer was started in another project and keeps running there. Switch back to that project to follow it here."
          : "The answer was still running when this chat was last open. QDash is attaching to it again without sending your message twice."}
      </p>
    </div>
  );
}
