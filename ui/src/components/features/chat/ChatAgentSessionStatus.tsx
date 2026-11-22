"use client";

import Link from "next/link";
import { Play } from "lucide-react";
import {
  getGetAgentInterventionQueryKey,
  getGetAgentSessionQueryKey,
  getListAgentActionCandidatesQueryKey,
  getListAgentActionsQueryKey,
  useGetAgentIntervention,
  useGetAgentSession,
  useListAgentActionCandidates,
  useListAgentActions,
} from "@/client/agent-session/agent-session";
import { projectRequest } from "@/components/features/agent-session/useLinkedProject";
import { useProject } from "@/contexts/ProjectContext";
import {
  agentSessionStatus,
  type AgentActionState,
  type AgentInterventionState,
  type AgentSessionState,
  type AgentSessionStatus,
} from "@/lib/chatAgentSession";

/** How often an open session's state is read again while the chat shows it. */
const REFRESH_MS = 15_000;

const PHASE_TONE: Record<AgentSessionStatus["phase"], string> = {
  measurement_running: "status-info",
  expert_waiting: "status-warning",
  expert_answered: "status-warning",
  next_decision: "status-warning",
  completed: "status-success",
  cancelled: "status-neutral",
  expired: "status-neutral",
};

/** What the chat itself is doing about the session's next decision. */
export type ChatTurnState = "live" | "detached" | "none";

/**
 * The next step, said plainly. An agent decision is made only by a chat turn: with none
 * running, the session waits until the user continues it; nothing starts on its own.
 */
function nextStep(status: AgentSessionStatus, chatTurn: ChatTurnState): string | null {
  switch (status.nextActor) {
    case "expert":
      return "Next: an expert answers the intervention.";
    case "measurement":
      return "Next: the measurement finishes; the agent reads it in its running turn.";
    case "agent":
      if (chatTurn === "live") return "Next: the agent decides in the turn running in this chat.";
      if (chatTurn === "detached") return "Next: the agent decides in the turn being reattached.";
      return "Next: the agent decides. No chat turn is running, so nothing happens until you continue.";
    default:
      return null;
  }
}

/**
 * The state of the calibration session this chat's tools act on, read from QDash under
 * the project open now: what runs or waits, who acts next, the latest measurement, and
 * its candidate values. A session QDash does not find in this project shows nothing.
 * `onContinue` offers an explicit Continue, sent as an ordinary chat message.
 */
export function ChatAgentSessionStatus({
  agentSessionId,
  chatTurn,
  onContinue,
}: {
  agentSessionId: string;
  chatTurn: ChatTurnState;
  onContinue?: () => void;
}) {
  const { projectId } = useProject();
  const enabled = projectId !== null;
  const request = projectId ? projectRequest(projectId) : undefined;
  const session = useGetAgentSession(agentSessionId, {
    query: {
      queryKey: [...getGetAgentSessionQueryKey(agentSessionId), projectId],
      enabled,
      retry: false,
      refetchInterval: (query) => {
        const status = query.state.data?.data.status;
        return status === "active" || status === "waiting_for_human" ? REFRESH_MS : false;
      },
    },
    request,
  });
  const data = session.data?.data as (AgentSessionState & { session_id: string }) | undefined;
  const open = data?.status === "active" || data?.status === "waiting_for_human";
  const interventionId = data?.active_intervention_id ?? "";
  const intervention = useGetAgentIntervention(agentSessionId, interventionId, {
    query: {
      queryKey: [
        ...getGetAgentInterventionQueryKey(agentSessionId, interventionId),
        projectId,
        // Read again whenever the session's own state is.
        session.dataUpdatedAt,
      ],
      enabled: enabled && Boolean(interventionId),
      retry: false,
    },
    request,
  });
  const actions = useListAgentActions(agentSessionId, {
    query: {
      queryKey: [...getListAgentActionsQueryKey(agentSessionId), projectId, session.dataUpdatedAt],
      enabled: enabled && Boolean(data),
      retry: false,
    },
    request,
  });
  const actionItems = (actions.data?.data.items ?? []) as (AgentActionState & {
    action_id: string;
  })[];
  const status = data
    ? agentSessionStatus(
        data,
        (intervention.data?.data as AgentInterventionState | undefined) ?? null,
        actionItems,
      )
    : null;
  // Candidates of the latest finished measurement, while the session is open.
  const lastFinished = [...actionItems]
    .reverse()
    .find((a) => a.action_type === "run_task" && a.execution_status === "completed");
  const candidates = useListAgentActionCandidates(agentSessionId, lastFinished?.action_id ?? "", {
    query: {
      queryKey: [
        ...getListAgentActionCandidatesQueryKey(agentSessionId, lastFinished?.action_id ?? ""),
        projectId,
      ],
      enabled: enabled && open && Boolean(lastFinished),
      retry: false,
    },
    request,
  });

  // Not found in this project, or not readable: say nothing rather than guess.
  if (!status || session.isError) return null;
  const step = nextStep(status, chatTurn);
  const candidateCount = candidates.data?.data.items.length ?? 0;
  const measurement = status.measurement;

  return (
    <section
      className="rounded-[var(--radius-box)] border border-base-300 bg-base-100 px-3 py-2.5 text-xs"
      aria-label="Calibration session"
      data-testid="chat-agent-session"
      data-phase={status.phase}
    >
      <div className="flex min-w-0 items-center gap-1.5">
        <span
          className={`status status-xs shrink-0 ${PHASE_TONE[status.phase]}`}
          aria-hidden="true"
        />
        <span role="status" className="truncate font-medium text-base-content/80">
          {status.label}
        </span>
        <Link
          href={`/agent-sessions/${encodeURIComponent(agentSessionId)}`}
          className="link link-hover ml-auto shrink-0 text-base-content/60"
        >
          Session
        </Link>
      </div>
      {measurement && (
        <p className="mt-1 truncate text-base-content/60">
          Latest measurement: {measurement.taskName}
          {measurement.qids.length ? ` on ${measurement.qids.join(", ")}` : ""} ·{" "}
          {measurement.status}
          {candidateCount > 0 && measurement.status === "completed"
            ? ` · ${candidateCount} candidate value${candidateCount === 1 ? "" : "s"}`
            : ""}
        </p>
      )}
      {step && <p className="mt-1 text-base-content/60">{step}</p>}
      {onContinue && status.nextActor === "agent" && chatTurn === "none" && (
        <button
          type="button"
          className="btn btn-xs btn-outline mt-2"
          onClick={onContinue}
          data-testid="continue-agent-session"
        >
          <Play data-icon="inline-start" aria-hidden="true" />
          Continue session
        </button>
      )}
    </section>
  );
}
