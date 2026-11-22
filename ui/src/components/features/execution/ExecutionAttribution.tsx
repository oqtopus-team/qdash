"use client";

import { Bot, UserRound } from "lucide-react";

import type { ExecutionAgentSessionLink } from "@/schemas";

type ActorFields = {
  user_id?: string | null;
  username?: string;
};

/** The recorded user of a row, or a placeholder; never the person viewing the page. */
export function recordedUserLabel(actor?: ActorFields | null, fallbackUsername?: string | null) {
  if (actor?.username) return `@${actor.username}`;
  if (actor?.user_id) return actor.user_id;
  if (fallbackUsername) return `@${fallbackUsername}`;
  return "Unknown";
}

/**
 * Whether an agent session's action dispatched this execution. Only the server's action link
 * counts: a tag or a name such as `agent:CheckRabi` is no evidence of who ran it.
 */
export function isAgentDispatched(
  link: ExecutionAgentSessionLink | null | undefined,
): link is ExecutionAgentSessionLink {
  return link?.linked === true;
}

/** "Agent · @user": the agent ran it on behalf of the user responsible for the session. */
export function AgentActorLabel({
  userLabel,
  className = "",
}: {
  userLabel: string;
  className?: string;
}) {
  return (
    <span className={`inline-flex min-w-0 items-center gap-1 ${className}`}>
      <span className="badge badge-outline badge-sm shrink-0 gap-1">
        <Bot className="h-3 w-3" aria-hidden="true" />
        Agent
      </span>
      <span aria-hidden="true">·</span>
      <span className="truncate">{userLabel}</span>
    </span>
  );
}

/**
 * Who ran an execution: the recorded user for a manual run, or "Agent · @user" when a verified
 * agent session action dispatched it. The user stays the recorded one in both cases.
 */
export function ExecutionActor({
  actor,
  link,
  iconClassName = "h-3 w-3 shrink-0",
}: {
  actor?: ActorFields | null;
  link?: ExecutionAgentSessionLink | null;
  iconClassName?: string;
}) {
  if (isAgentDispatched(link)) {
    return <AgentActorLabel userLabel={recordedUserLabel(actor, link.created_by)} />;
  }
  return (
    <span className="inline-flex min-w-0 items-center gap-1">
      <UserRound className={iconClassName} aria-hidden="true" />
      <span className="truncate">{recordedUserLabel(actor)}</span>
    </span>
  );
}
