"use client";

import { Check, CircleHelp, PenLine, ShieldCheck, X } from "lucide-react";
import type { ApprovalRequest, AskRequest } from "@/types/copilotChat";

/** How a card behaves: open for an answer, or showing the answer it got. */
export interface InteractionState {
  /** The card is on the latest answer and nothing is streaming. */
  active: boolean;
  /** The user's reply, when one follows this answer. */
  answer?: string;
  onAnswer: (text: string) => void;
  onDecide: (approvalId: string, approve: boolean, label: string) => void;
  /** Move focus to the composer so the user can type their own answer. */
  onOther: () => void;
}

function approvedText(approval: ApprovalRequest): string {
  return `Approved: ${approval.label}`;
}

function declinedText(approval: ApprovalRequest): string {
  return `Declined: ${approval.label}`;
}

export function AskCard({ ask, state }: { ask: AskRequest; state: InteractionState }) {
  return (
    <div className="chat-interaction-card not-prose" role="group" aria-label={ask.question}>
      <div className="flex items-start gap-2 mb-2.5">
        <CircleHelp className="w-4 h-4 mt-0.5 text-primary shrink-0" />
        <p className="text-sm font-medium leading-snug">{ask.question}</p>
      </div>
      <div className="flex flex-col gap-1.5">
        {ask.options.map((option, i) => {
          const chosen = state.answer === option.label;
          return (
            <button
              key={option.label}
              type="button"
              disabled={!state.active}
              onClick={() => state.onAnswer(option.label)}
              className={`chat-option ${chosen ? "chat-option-chosen" : ""}`}
            >
              <span className="chat-option-key">{i + 1}</span>
              <span className="min-w-0 flex-1 text-left">
                <span className="block text-sm font-medium">{option.label}</span>
                {option.description && (
                  <span className="block text-xs text-base-content/55 mt-0.5">
                    {option.description}
                  </span>
                )}
              </span>
              {chosen && <Check className="w-4 h-4 text-primary shrink-0" />}
            </button>
          );
        })}
        {state.active && (
          <button type="button" onClick={state.onOther} className="chat-option chat-option-other">
            <PenLine className="w-3.5 h-3.5 text-base-content/45" />
            <span className="text-sm text-base-content/60">Something else…</span>
          </button>
        )}
      </div>
    </div>
  );
}

function ArgValue({ value }: { value: unknown }) {
  if (value !== null && typeof value === "object") {
    return (
      <pre className="text-[11px] leading-relaxed font-mono whitespace-pre-wrap break-all bg-base-200/70 rounded-md px-2 py-1 m-0">
        {JSON.stringify(value, null, 2)}
      </pre>
    );
  }
  return <span className="font-mono text-xs break-all">{String(value)}</span>;
}

export function ApprovalCard({
  approval,
  state,
}: {
  approval: ApprovalRequest;
  state: InteractionState;
}) {
  const decided =
    state.answer === approvedText(approval)
      ? "approved"
      : state.answer === declinedText(approval)
        ? "declined"
        : null;
  const entries = Object.entries(approval.args);

  return (
    <div
      className="chat-interaction-card chat-approval-card not-prose"
      role="group"
      aria-label={`Approve ${approval.label}`}
    >
      <div className="flex items-start gap-2">
        <ShieldCheck className="w-4 h-4 mt-0.5 text-warning shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold leading-snug">{approval.label}</p>
          <p className="text-xs text-base-content/55 mt-0.5">
            This changes QDash. It runs only if you approve, with exactly these arguments.
          </p>
        </div>
      </div>

      {entries.length > 0 && (
        <dl className="mt-3 grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-xs">
          {entries.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="text-base-content/50 font-mono">{key}</dt>
              <dd className="m-0 min-w-0">
                <ArgValue value={value} />
              </dd>
            </div>
          ))}
        </dl>
      )}
      <p className="mt-2 text-[11px] font-mono text-base-content/35">{approval.tool}</p>

      <div className="mt-3 flex items-center gap-2">
        {decided ? (
          <span
            className={`inline-flex items-center gap-1.5 text-xs font-medium ${
              decided === "approved" ? "text-success" : "text-base-content/55"
            }`}
          >
            {decided === "approved" ? (
              <Check className="w-3.5 h-3.5" />
            ) : (
              <X className="w-3.5 h-3.5" />
            )}
            {decided === "approved" ? "Approved" : "Declined"}
          </span>
        ) : state.active ? (
          <>
            <button
              type="button"
              className="btn btn-primary btn-sm gap-1.5"
              onClick={() => state.onDecide(approval.id, true, approvedText(approval))}
            >
              <Check className="w-3.5 h-3.5" />
              Approve
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => state.onDecide(approval.id, false, declinedText(approval))}
            >
              Decline
            </button>
          </>
        ) : (
          <span className="text-xs text-base-content/45">No decision was made</span>
        )}
      </div>
    </div>
  );
}
