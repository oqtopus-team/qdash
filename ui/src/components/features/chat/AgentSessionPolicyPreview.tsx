"use client";

import type { ReactNode } from "react";

type Bounds = { minimum?: number | null; maximum?: number | null };

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function boundsText(value: unknown): string {
  const bounds = (record(value) ?? {}) as Bounds;
  const min = typeof bounds.minimum === "number" ? String(bounds.minimum) : "-inf";
  const max = typeof bounds.maximum === "number" ? String(bounds.maximum) : "inf";
  return `[${min}, ${max}]`;
}

/** Whether an approval argument holds an agent session policy this preview can summarize. */
export function isAgentSessionPolicy(value: unknown): value is Record<string, unknown> {
  const policy = record(value);
  return Boolean(policy && Array.isArray(policy.qids) && Array.isArray(policy.allowed_tasks));
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="contents">
      <dt className="text-base-content/60">{label}</dt>
      <dd className="m-0 min-w-0 wrap-anywhere">{children}</dd>
    </div>
  );
}

/**
 * The permissions an agent session grants, summarized before the user approves it. The
 * exact policy stays in the argument list below; this states what runs without asking again,
 * above all whether parameter updates (and backend applies) are part of the approval.
 */
export function AgentSessionPolicyPreview({
  policy,
  expiresInSeconds,
}: {
  policy: Record<string, unknown>;
  expiresInSeconds?: unknown;
}) {
  const overrides = Object.entries(record(policy.allowed_overrides) ?? {});
  const gates = Object.entries(record(policy.quality_gates) ?? {});
  const autonomy = policy.autonomy === "auto" ? "auto" : "confirm_each";
  const updates = record(policy.parameter_updates);
  const maxActions = typeof policy.max_actions === "number" ? policy.max_actions : 100;
  const expiry =
    typeof expiresInSeconds === "number"
      ? `${Math.round(expiresInSeconds / 60)} min`
      : "QDash default (6 h)";
  return (
    <div className="flex flex-col gap-2" data-testid="agent-session-policy-preview">
      <dl className="m-0 grid grid-cols-[fit-content(40%)_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
        <Row label="Qubits">
          <span className="font-mono">{strings(policy.qids).join(", ")}</span>
        </Row>
        <Row label="Tasks">
          <span className="font-mono">{strings(policy.allowed_tasks).join(", ")}</span>
        </Row>
        <Row label="Bounds">
          {overrides.length ? (
            <span className="font-mono">
              {overrides.map(([name, value]) => `${name} ${boundsText(value)}`).join("; ")}
            </span>
          ) : (
            "none"
          )}
        </Row>
        {gates.length > 0 && (
          <Row label="Quality gates">
            <span className="font-mono">
              {gates.map(([name, value]) => `${name} ${boundsText(value)}`).join("; ")}
            </span>
          </Row>
        )}
        <Row label="Steps">
          {autonomy === "auto"
            ? `run without asking, up to ${maxActions} actions`
            : `each action asks you, up to ${maxActions}`}
        </Row>
        <Row label="Expires">{expiry}</Row>
        <Row label="Parameter updates">
          {updates ? (
            <span className="flex flex-wrap items-center gap-1">
              <span className="badge badge-warning badge-xs">granted</span>
              <span className="font-mono">{strings(updates.parameters).join(", ")}</span>
              <span>from</span>
              <span className="font-mono">{strings(updates.tasks).join(", ")}</span>
              <span className="badge badge-ghost badge-xs">
                {updates.apply_backend === true ? "backend apply granted" : "no backend apply"}
              </span>
            </span>
          ) : (
            <span className="badge badge-ghost badge-xs">not granted: each commit asks you</span>
          )}
        </Row>
      </dl>
      {updates && (
        <p className="text-xs text-base-content/60">
          Approving lets the agent commit these parameters
          {updates.apply_backend === true ? " and write them to the backend" : ""} after a result it
          assesses as pass and QDash&apos;s bounds, quality gates, and task checks hold. A failed,
          uncertain, or unexplained result stops for a person instead.
        </p>
      )}
    </div>
  );
}
