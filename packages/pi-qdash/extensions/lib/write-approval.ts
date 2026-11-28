/**
 * Approval of one reviewed QDash write (tool-policy.ts `REVIEWED_WRITE_TOOL_NAMES`).
 *
 * The approval always comes from the host, never from the call's arguments: a
 * model can put anything into a tool call, so no argument (such as the former
 * `confirmWrite`) approves a write. A reviewed write runs only when one of
 * these approved exactly this call:
 *
 * - the pi CLI write gate (write-gate.ts), after the user accepted its
 *   confirmation dialog. The gate records a canonical snapshot of the
 *   arguments the dialog showed, bound to the tool name and call id; the tool
 *   consumes it once and runs only when its arguments still equal it;
 * - a host that collected the user's approval in its own UI and runs the call
 *   with `HOST_WRITE_APPROVAL_KEY` in the extension context naming the call
 *   and tool (the QDash web Agent's approval card, agent-runtime
 *   `runApproved`, which passes a frozen copy of the approved arguments);
 * - otherwise the tool's own confirmation dialog, when the host has a UI. The
 *   call runs only when its arguments did not change while the dialog was open.
 *
 * Every dialog shows the complete canonical arguments it approves
 * (`approvalReviewText`) through write-review.ts, which scrolls in the pi
 * terminal UI and refuses approval until the user displayed the end.
 *
 * A call that names a stored pipeline plan (`qdash_run_pipeline` with
 * `planId`) also needs the plan the user was shown: each of these fetches it
 * before asking (pipeline-plan-preview.ts), shows its resolved content, and
 * binds the approval to it. `requireWriteApproval` returns that preview; the
 * tool runs the plan with its review digest, never one from the arguments.
 *
 * Without a UI and without either approval the write is refused. Arguments
 * that are not plain JSON data cannot be shown or compared and are refused.
 * The session-granted tools (`SESSION_GRANTED_WRITE_TOOL_NAMES`) do not use
 * this: the user approved their bounded session once, and QDash checks each call.
 */

import { formatPlanApprovalPreview, needsApprovalPreview, type ApprovalPreview } from "./pipeline-plan-preview.js";
import { reviewWrite, type WriteReviewUI } from "./write-review.js";

/**
 * Extension-context field through which a host passes an approval its own UI
 * collected: the call id and tool name of the one call the user approved. Only
 * host code builds the extension context; a model cannot set it.
 */
export const HOST_WRITE_APPROVAL_KEY = "qdashWriteApproval";

export interface HostWriteApproval {
  toolCallId: string;
  toolName: string;
  /** What the host fetched and showed with the call, for a call that needs it. */
  preview?: ApprovalPreview;
}

export interface WriteApprovalContext {
  hasUI?: boolean;
  /** pi's run mode: `"tui"` reviews in a scrollable overlay, `"rpc"` sends the text to the client. */
  mode?: string;
  ui?: WriteReviewUI;
  /** pi's abort signal of the running agent turn; an aborted call is never approved. */
  signal?: AbortSignal;
  [HOST_WRITE_APPROVAL_KEY]?: HostWriteApproval;
}

export interface WriteDialog {
  title: string;
  /** What the write does; the complete arguments are appended to it. */
  message: string;
  /**
   * For a call that needs a preview: fetch it for the tool's own dialog. The gate and a host
   * fetch it themselves before they ask.
   */
  preview?: () => Promise<ApprovalPreview>;
}

/**
 * The text a review shows: `summary` (what the write does, such as a
 * session's grant) followed by every argument of the canonical snapshot
 * `approvedArgs`, in full. Nothing is shortened: the review scrolls.
 */
export function approvalReviewText(summary: string, approvedArgs: string): string {
  const listing = JSON.stringify(JSON.parse(approvedArgs), null, 2);
  return [summary, "", "Arguments (the approval covers exactly these):", listing].join("\n");
}

class NotPlainData extends Error {}

function encode(value: unknown, ancestors: Set<object>): string {
  if (value === null) return "null";
  switch (typeof value) {
    case "string":
      return JSON.stringify(value);
    case "boolean":
      return value ? "true" : "false";
    case "number":
      if (!Number.isFinite(value)) throw new NotPlainData();
      return JSON.stringify(value);
    case "object":
      break;
    default:
      throw new NotPlainData();
  }
  const object = value as object;
  if (ancestors.has(object)) throw new NotPlainData();
  ancestors.add(object);
  try {
    if (Array.isArray(object)) {
      if (Object.getPrototypeOf(object) !== Array.prototype) throw new NotPlainData();
      const keys = Reflect.ownKeys(object);
      // Indices and `length` only: no holes, extra keys, or accessors.
      if (keys.length !== object.length + 1) throw new NotPlainData();
      const items: string[] = [];
      for (let index = 0; index < object.length; index += 1) {
        const descriptor = Object.getOwnPropertyDescriptor(object, String(index));
        if (!descriptor || !("value" in descriptor)) throw new NotPlainData();
        items.push(encode(descriptor.value, ancestors));
      }
      return `[${items.join(",")}]`;
    }
    const prototype = Object.getPrototypeOf(object);
    if (prototype !== Object.prototype && prototype !== null) throw new NotPlainData();
    const entries: Array<[string, string]> = [];
    for (const key of Reflect.ownKeys(object)) {
      if (typeof key !== "string") throw new NotPlainData();
      const descriptor = Object.getOwnPropertyDescriptor(object, key);
      if (!descriptor || !("value" in descriptor)) throw new NotPlainData();
      // JSON has no undefined: such a property is absent from what is sent.
      if (descriptor.value === undefined) continue;
      entries.push([key, encode(descriptor.value, ancestors)]);
    }
    entries.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${item}`).join(",")}}`;
  } finally {
    ancestors.delete(object);
  }
}

/**
 * The canonical form of tool arguments: JSON with object keys sorted and
 * properties whose value is undefined left out, so key order never matters.
 * Undefined when the arguments are not plain JSON data (a cycle, a function,
 * a class instance, an accessor, a symbol key, a non-finite number), which can
 * be neither shown to the user nor compared, so no approval covers them.
 */
export function canonicalArgs(value: unknown): string | undefined {
  try {
    return encode(value, new Set());
  } catch {
    return undefined;
  }
}

interface GateApproval {
  toolName: string;
  args: string;
  preview?: ApprovalPreview;
}

// Calls the write gate's dialog approved, by tool call id: the tool name and
// the canonical arguments the dialog showed. Each is consumed by the tool's
// first approval check and forgotten when the call ends without running.
const gateApprovals = new Map<string, GateApproval>();

/**
 * Record that the user approved `toolName` call `toolCallId` with canonical arguments `args`,
 * and the preview the dialog showed with them, when the call needed one.
 */
export function recordGateApproval(toolCallId: string, toolName: string, args: string, preview?: ApprovalPreview): void {
  gateApprovals.set(toolCallId, { toolName, args, ...(preview ? { preview: deepFrozen(structuredClone(preview)) } : {}) });
}

function deepFrozen<T>(value: T): T {
  if (value !== null && typeof value === "object") {
    for (const item of Object.values(value)) deepFrozen(item);
    Object.freeze(value);
  }
  return value;
}

/** Forget an approval the gate recorded for a call that will not run. */
export function forgetGateApproval(toolCallId: string): void {
  gateApprovals.delete(toolCallId);
}

/** Whether an unconsumed gate approval exists for `toolCallId` (tests and diagnostics). */
export function hasGateApproval(toolCallId: string): boolean {
  return gateApprovals.has(toolCallId);
}

function hostApproved(ctx: WriteApprovalContext | undefined, toolName: string, toolCallId: string): boolean {
  const approval = ctx?.[HOST_WRITE_APPROVAL_KEY];
  return (
    typeof approval === "object" &&
    approval !== null &&
    approval.toolCallId === toolCallId &&
    approval.toolName === toolName
  );
}

/** Why a write was refused in a session that has no UI to ask the user in. */
export function noApprovalMessage(toolName: string): string {
  return (
    `${toolName} requires explicit confirmation: it is a QDash write the user approves in a ` +
    "confirmation dialog, and this session has no UI to ask in, so it was not run. No " +
    "argument (such as confirmWrite) approves a write; run it in an interactive pi session " +
    "or the QDash Agent."
  );
}

/** Why a write whose arguments are not plain JSON data was refused. */
export function unserializableArgsMessage(toolName: string): string {
  return `${toolName} was not run: its arguments are not plain JSON data, so they cannot be shown for approval or checked against it.`;
}

/** Why a write whose arguments changed after the user saw them was refused. */
export function changedArgsMessage(toolName: string): string {
  return `${toolName} was not run: its arguments changed after the user saw them in the confirmation dialog, so that approval does not cover this call.`;
}

/** Why a write cancelled while it waited for the user was refused. */
export function cancelledApprovalMessage(toolName: string): string {
  return `${toolName} was not run: the turn was cancelled before the write was approved.`;
}

/** The text a review of a call shows: the preview the call needs first, then the arguments. */
export function previewReviewText(summary: string, approvedArgs: string, preview: ApprovalPreview | undefined): string {
  return approvalReviewText(preview ? `${summary}\n\n${formatPlanApprovalPreview(preview)}` : summary, approvedArgs);
}

/** Why a call that needs a preview was approved without one. */
export function missingPreviewMessage(toolName: string): string {
  return `${toolName} was not run: its approval does not carry the stored plan the user was shown, so it covers no plan. Call it again so QDash's plan is shown for approval.`;
}

/**
 * Return when the host approved this call; otherwise ask the user with
 * `dialog`, or throw when the user declines, no UI exists, the turn is
 * cancelled, or the arguments differ from what the user approved.
 *
 * Returns the preview the approval showed, for a call that needs one
 * (`needsApprovalPreview`), and undefined for every other call. A call that
 * needs one and was approved without it is refused.
 */
export async function requireWriteApproval(
  toolName: string,
  toolCallId: string,
  params: object,
  ctx: WriteApprovalContext | undefined,
  dialog: WriteDialog,
): Promise<ApprovalPreview | undefined> {
  const needsPreview = needsApprovalPreview(toolName, params);
  const signal = ctx?.signal;
  if (signal?.aborted) {
    forgetGateApproval(toolCallId);
    throw new Error(cancelledApprovalMessage(toolName));
  }
  const gate = gateApprovals.get(toolCallId);
  if (gate !== undefined) {
    // Single use: whatever the outcome, this approval is spent.
    gateApprovals.delete(toolCallId);
    if (gate.toolName !== toolName || canonicalArgs(params) !== gate.args) throw new Error(changedArgsMessage(toolName));
    if (needsPreview && !gate.preview) throw new Error(missingPreviewMessage(toolName));
    return needsPreview ? gate.preview : undefined;
  }
  if (hostApproved(ctx, toolName, toolCallId)) {
    if (canonicalArgs(params) === undefined) throw new Error(unserializableArgsMessage(toolName));
    const preview = ctx?.[HOST_WRITE_APPROVAL_KEY]?.preview;
    if (needsPreview && !preview) throw new Error(missingPreviewMessage(toolName));
    return needsPreview ? preview : undefined;
  }
  if (!ctx?.hasUI || !ctx.ui) throw new Error(noApprovalMessage(toolName));
  const shown = canonicalArgs(params);
  if (shown === undefined) throw new Error(unserializableArgsMessage(toolName));
  let preview: ApprovalPreview | undefined;
  if (needsPreview) {
    if (!dialog.preview) throw new Error(missingPreviewMessage(toolName));
    preview = deepFrozen(structuredClone(await dialog.preview()));
  }
  const ok = await reviewWrite(
    { mode: ctx.mode, ui: ctx.ui },
    dialog.title,
    previewReviewText(`${toolName}: ${dialog.message}`, shown, preview),
    signal,
  );
  if (signal?.aborted) throw new Error(cancelledApprovalMessage(toolName));
  if (!ok) throw new Error(`${toolName} requires explicit confirmation`);
  if (canonicalArgs(params) !== shown) throw new Error(changedArgsMessage(toolName));
  return preview;
}
