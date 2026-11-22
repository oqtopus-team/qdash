"use client";

import Link from "next/link";

import { Bot } from "lucide-react";

import type { ExecutionAgentSessionLink } from "@/schemas";

import { sessionStatusLabel } from "@/components/features/agent-session/interventionLabels";

import { sessionGraphHref } from "./agentSessionDisplay";

/**
 * Where an execution sits in an agent session. A linked execution points to its session's
 * graph and names the user responsible for the session, apart from the agent that ran it;
 * one only tagged for a session says so, because the tag is no link and the execution stays
 * an ordinary one with no agent attribution.
 */
export function ExecutionAgentSessionNotice({
  link,
  chipId,
  className = "",
}: {
  link: ExecutionAgentSessionLink | null | undefined;
  chipId: string;
  className?: string;
}) {
  if (!link) return null;
  if (!link.linked) {
    return (
      <div role="note" className={`alert alert-soft text-sm ${className}`}>
        <Bot className="h-4 w-4" aria-hidden="true" />
        <span>
          Tagged for agent session <span className="font-mono">{link.session_id}</span>, but no
          action of that session dispatched it on this chip, so it is listed as its own execution
        </span>
      </div>
    );
  }
  return (
    <div role="note" className={`alert alert-info alert-soft text-sm ${className}`}>
      <Bot className="h-4 w-4" aria-hidden="true" />
      <div className="flex flex-col gap-0.5">
        <span>
          One measurement of agent session <span className="font-mono">{link.session_id}</span>
          {link.status ? ` (${sessionStatusLabel(link.status)})` : ""}
        </span>
        <span>
          Run by an agent;{" "}
          {link.created_by
            ? `@${link.created_by} created the session and is responsible for it.`
            : "the session records no creator."}
          {link.model_name ? ` Model: ${link.model_name}.` : ""} Expert answers and commits keep
          their own users in the session audit.
        </span>
      </div>
      <Link href={sessionGraphHref(chipId, link.session_id)} className="link link-hover">
        Open session graph
      </Link>
    </div>
  );
}
