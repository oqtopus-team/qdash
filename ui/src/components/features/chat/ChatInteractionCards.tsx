"use client";

import { useState } from "react";
import { Check, CircleHelp, FileDiff, PenLine, ShieldCheck, X } from "lucide-react";
import { CodeBlock } from "@/components/features/chat/CodeBlock";
import { PipelinePreview, isPipelineSpec } from "@/components/features/chat/PipelinePreview";
import { PierreDiffViewer } from "@/components/ui/PierreDiffViewer";
import type { ApprovalRequest, AskRequest, EditProposal } from "@/types/copilotChat";

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
  /** Put proposed code into the open editor; absent or false when no editor is open. */
  applyCode?: (edit: EditProposal) => boolean;
  /** The code the open editor holds now, for the diff of a proposal. */
  currentCode?: (edit: EditProposal) => string | null;
}

function stringArg(args: Record<string, unknown>, key: string): string | null {
  const value = args[key];
  return typeof value === "string" && value.trim() ? value : null;
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

/** Arguments a flow save shows as a preview instead of in the argument list. */
const FLOW_PREVIEW_KEYS = new Set(["name", "code", "description", "chipId", "tags"]);

/** A flow about to be saved: what it is called, which chip, and the whole code to review. */
function FlowSavePreview({ args }: { args: Record<string, unknown> }) {
  const name = stringArg(args, "name");
  const chipId = stringArg(args, "chipId");
  const description = stringArg(args, "description");
  const tags = Array.isArray(args.tags)
    ? args.tags.filter((t): t is string => typeof t === "string")
    : [];
  const code = stringArg(args, "code") ?? "";
  return (
    <div
      className="rounded-lg border border-base-300/70 bg-base-100/60 p-3"
      data-testid="flow-save-preview"
    >
      <div className="text-xs">
        Flow <span className="font-mono font-medium">{name ?? "?"}</span>
        {chipId ? (
          <>
            {" "}
            on chip <span className="font-mono">{chipId}</span>
          </>
        ) : (
          " on the session's chip"
        )}
        {tags.map((tag) => (
          <span key={tag} className="badge badge-ghost badge-xs ml-1 align-middle">
            {tag}
          </span>
        ))}
      </div>
      {description && <p className="mt-0.5 text-xs text-base-content/60">{description}</p>}
      <div className="max-h-96 overflow-auto">
        <CodeBlock compact language="python">
          {code}
        </CodeBlock>
      </div>
      <p className="text-xs text-base-content/50">
        QDash checks the @flow function, formats the file, and registers the deployment. A flow of
        the same name is replaced. Saving does not run it.
      </p>
    </div>
  );
}

const METRIC_SCRIPT_PREVIEW_KEYS = new Set(["name", "source", "description", "visibility"]);

/** A metric script about to be saved: its name, sharing, and the whole source to review. */
function MetricScriptSavePreview({ args }: { args: Record<string, unknown> }) {
  const name = stringArg(args, "name");
  const scriptId = stringArg(args, "scriptId");
  const visibility = stringArg(args, "visibility");
  const description = stringArg(args, "description");
  const source = stringArg(args, "source") ?? "";
  return (
    <div
      className="rounded-lg border border-base-300/70 bg-base-100/60 p-3"
      data-testid="metric-script-save-preview"
    >
      <div className="text-xs">
        {scriptId ? "Update" : "New"} metric script{" "}
        <span className="font-mono font-medium">{name ?? "?"}</span>
        {visibility && (
          <span className="badge badge-ghost badge-xs ml-1 align-middle">
            {visibility === "project" ? "shared with project" : visibility}
          </span>
        )}
      </div>
      {description && <p className="mt-0.5 text-xs text-base-content/60">{description}</p>}
      <div className="max-h-96 overflow-auto">
        <CodeBlock compact language="python" title={`${name ?? "script"}.py`}>
          {source}
        </CodeBlock>
      </div>
      <p className="text-xs text-base-content/50">
        QDash validates the script before saving it. Text that fails validation is saved as a new
        revision, but dashboards keep using the last revision that validated.
      </p>
    </div>
  );
}

function ArgValue({ value }: { value: unknown }) {
  if (value !== null && typeof value === "object") {
    return (
      <pre className="text-xs leading-relaxed font-mono whitespace-pre-wrap break-all bg-base-200/70 rounded-md px-2 py-1 m-0">
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
  // A pipeline spec gets its own preview; the other arguments stay in the list.
  const pipelineSpec = isPipelineSpec(approval.args.spec) ? approval.args.spec : null;
  const chipId = stringArg(approval.args, "chipId") ?? stringArg(approval.args, "chip_id");
  // A flow save shows its code as code; the remaining arguments stay in the list.
  const flowSave = approval.tool === "qdash_save_flow" && typeof approval.args.code === "string";
  // A metric script save shows its source the same way.
  const scriptSave =
    approval.tool === "qdash_save_metric_script" && typeof approval.args.source === "string";
  const entries = Object.entries(approval.args).filter(
    ([key]) =>
      !(pipelineSpec && key === "spec") &&
      !(flowSave && FLOW_PREVIEW_KEYS.has(key)) &&
      !(scriptSave && METRIC_SCRIPT_PREVIEW_KEYS.has(key)),
  );

  return (
    <div
      className="chat-interaction-card chat-approval-card not-prose"
      role="group"
      aria-label={`Approve ${approval.label}`}
    >
      <div className="flex items-start gap-2">
        <ShieldCheck className="w-4 h-4 mt-0.5 text-warning shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-snug">{approval.label}</p>
          <p className="text-xs text-base-content/55 mt-0.5">
            This changes QDash. It runs only if you approve, with exactly these arguments.
          </p>
        </div>
      </div>

      {pipelineSpec && (
        <div className="mt-3">
          <PipelinePreview chipId={chipId} spec={pipelineSpec} />
        </div>
      )}
      {flowSave && (
        <div className="mt-3">
          <FlowSavePreview args={approval.args} />
        </div>
      )}
      {scriptSave && (
        <div className="mt-3">
          <MetricScriptSavePreview args={approval.args} />
        </div>
      )}

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
      <p className="mt-2 text-xs font-mono text-base-content/35">{approval.tool}</p>

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
              className="btn btn-primary btn-sm"
              onClick={() => state.onDecide(approval.id, true, approvedText(approval))}
            >
              <Check data-icon="inline-start" />
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

/**
 * A change the assistant proposes to the flow open in the Workflow editor, to
 * the metric script open in its editor, or to a custom dashboard's draft: the
 * diff against what the page holds now, applied there with one click. The card
 * never saves; the page's Save does, through QDash's validation.
 */
export function EditProposalCard({ edit, state }: { edit: EditProposal; state: InteractionState }) {
  const isScript = edit.target === "metric_script";
  const isDashboard = edit.target === "dashboard";
  const name =
    (isScript ? edit.scriptName || edit.flowName : edit.flowName) ||
    (isDashboard ? "new dashboard" : "script");
  const filename = isDashboard ? "dashboard.json" : `${name}.py`;
  const language = isDashboard ? "json" : "python";
  const [outcome, setOutcome] = useState<"applied" | "discarded" | null>(null);
  // The editor text the diff was made against. The chat does not rerender as
  // the user types in the editor, so Apply reads the text again first and, when
  // it changed, shows the new diff instead of overwriting what they typed.
  const [base, setBase] = useState<string | null>(() => state.currentCode?.(edit) ?? null);
  const [changed, setChanged] = useState(false);
  const current = base;
  const canApply = Boolean(state.applyCode) && current !== null && outcome === null;
  const unchanged = current !== null && current === edit.code;
  const apply = () => {
    const live = state.currentCode?.(edit) ?? null;
    if (live !== base) {
      setBase(live);
      setChanged(true);
      return;
    }
    if (state.applyCode?.(edit)) setOutcome("applied");
  };
  return (
    <div
      className="chat-interaction-card not-prose"
      role="group"
      aria-label={`Proposed change to ${name}`}
      data-testid="edit-proposal"
    >
      <div className="flex items-start gap-2">
        <FileDiff className="w-4 h-4 mt-0.5 text-primary shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-snug">
            Proposed change to {isScript ? "metric script " : isDashboard ? "dashboard " : ""}
            <span className={isDashboard ? undefined : "font-mono"}>{name}</span>
          </p>
          <p className="text-xs text-base-content/70 mt-0.5">{edit.summary}</p>
        </div>
      </div>
      <div className="mt-3 max-h-[28rem] overflow-auto rounded-lg border border-base-300/70">
        {current !== null && !unchanged ? (
          <PierreDiffViewer filename={filename} oldContent={current} newContent={edit.code} />
        ) : (
          <CodeBlock compact language={language} title={filename}>
            {edit.code}
          </CodeBlock>
        )}
      </div>
      {unchanged && (
        <p className="mt-2 text-xs text-base-content/50">
          {isDashboard ? "The draft already holds this." : "The editor already holds this code."}
        </p>
      )}
      {changed && outcome === null && (
        <p className="mt-2 text-xs text-warning" role="status">
          {isDashboard
            ? "The dashboard draft changed since this diff was made. Review the updated diff, then apply."
            : "The editor changed since this diff was made. Review the updated diff, then apply."}
        </p>
      )}
      {(!state.applyCode || current === null) && (
        <p className="mt-2 text-xs text-base-content/50">
          {isDashboard
            ? "Open this dashboard, as a member who can edit it, to apply the change to its draft."
            : isScript
              ? "Open this metric script in its editor to apply the change there."
              : "Open this flow in the Workflow editor on the same chip to apply the change there."}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {outcome === "applied" && (
          <span className="inline-flex items-center gap-1 text-xs text-success">
            <Check className="w-3.5 h-3.5" />
            {isDashboard
              ? "Applied to the dashboard draft. Review the panels, then Save."
              : "Applied to the editor. Review it, then Save."}
          </span>
        )}
        {outcome === "discarded" && (
          <span className="inline-flex items-center gap-1 text-xs text-base-content/50">
            <X className="w-3.5 h-3.5" /> Discarded
          </span>
        )}
        {canApply && (
          <>
            <button type="button" className="btn btn-primary btn-xs" onClick={apply}>
              {isDashboard ? "Apply to draft" : "Apply to editor"}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-xs"
              onClick={() => setOutcome("discarded")}
            >
              Discard
            </button>
          </>
        )}
      </div>
    </div>
  );
}
