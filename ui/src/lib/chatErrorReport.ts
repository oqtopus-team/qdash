/**
 * A bug-report draft for a chat answer that ended with an application error.
 *
 * The draft is text the user reads, edits, and posts themselves: QDash files nothing, sends
 * nothing to GitHub, and puts nothing in the issue URL. It states only facts QDash knows
 * without the error's own text: the kind of failure, an HTTP status, an allowlisted page category, the draft generation time, and the chat id. The raw message is left out, because a runtime or
 * proxy error can quote prompts, URLs, tokens, model endpoints, or results.
 */

/** The repository's own bug-report form (.github/ISSUE_TEMPLATE/BUG_REPORT.yaml). */
export const BUG_REPORT_URL =
  "https://github.com/oqtopus-team/qdash/issues/new?template=BUG_REPORT.yaml";

type ChatErrorKind =
  /** The server answered 5xx: QDash or the Agent runtime failed. */
  | "server_error"
  /** The stream ended without its result, or the response had no body. */
  | "interrupted"
  /** An error message without enough structured information to identify its source. */
  | "unclassified_error"
  /** A 4xx answer: sign-in, permission, limits, or input to correct; not reported as a bug. */
  | "request_refused";

export interface ChatErrorClassification {
  kind: ChatErrorKind;
  /** HTTP status, when the message carries one. */
  status: number | null;
  /** Whether the failure looks like an application fault worth a bug report. */
  reportable: boolean;
}

const HTTP_STATUS = /^HTTP (\d{3})\b/;
const INTERRUPTED = new Set([
  "The connection closed before the answer was complete",
  "No response body",
]);

/** Sort a chat error by what QDash can tell from its form, never by guessing at its text. */
export function classifyChatError(message: string): ChatErrorClassification {
  const match = HTTP_STATUS.exec(message.trim());
  if (match) {
    const status = Number(match[1]);
    return status >= 500
      ? { kind: "server_error", status, reportable: true }
      : { kind: "request_refused", status, reportable: false };
  }
  if (INTERRUPTED.has(message.trim())) {
    return { kind: "interrupted", status: null, reportable: true };
  }
  return { kind: "unclassified_error", status: null, reportable: true };
}

const KIND_TEXT: Record<ChatErrorKind, string> = {
  server_error: "The server answered with an error status",
  interrupted: "The answer stream ended before its result arrived",
  unclassified_error: "The chat reported an error; its source is not established",
  request_refused: "The request was refused",
};

export interface ChatErrorReportInput {
  message: string;
  /** The page path; only a known top-level page category is retained. */
  path?: string;
  /** The chat's id, offered for the user to keep or delete. */
  chatId?: string | null;
  /** When this draft is generated, not when the error occurred. */
  at?: Date;
}

/** Never copy arbitrary path segments: they may contain credentials or private names. */
export function reportPageCategory(path: string): string {
  const pathname = path.split(/[?#]/, 1)[0];
  if (pathname === "/") return "/";
  const category = pathname.split("/")[1];
  const allowed = new Set([
    "chat",
    "home",
    "metrics",
    "settings",
    "tasks",
    "inbox",
    "analysis",
    "evaluations",
    "task-results",
    "config",
    "chip",
    "admin",
    "forum",
    "knowledge",
    "dashboards",
    "workflow",
    "execution",
    "agent-sessions",
  ]);
  return pathname.startsWith("/") && allowed.has(category)
    ? `/${category}${pathname === `/${category}` ? "" : "/[redacted]"}`
    : "[not included]";
}

/** The draft, in the order of the repository's bug-report form. */
export function buildChatErrorReport(input: ChatErrorReportInput): string {
  const { kind, status } = classifyChatError(input.message);
  const observed = `${KIND_TEXT[kind]}${status !== null ? ` (HTTP ${status})` : ""}.`;
  const at = (input.at ?? new Date()).toISOString();
  return [
    "### Describe the bug",
    `A QDash Agent chat answer ended with an error. ${observed}`,
    "",
    "### To Reproduce",
    "1. (What you asked, in your own words. Leave out private data.)",
    "2. (What the Agent was doing when it stopped, for example the tool it was running.)",
    "",
    "### Expected behavior",
    "The answer completes, or reports a failure of the operation itself.",
    "",
    "### Observed",
    observed,
    "",
    "### Confirmed facts (recorded by QDash)",
    `- Failure kind: ${kind}`,
    `- HTTP status: ${status ?? "none"}`,
    `- Page: ${reportPageCategory(input.path ?? "/")}`,
    `- Draft generated at (UTC): ${at}`,
    ...(input.chatId ? [`- Chat id (delete this line if you prefer): ${input.chatId}`] : []),
    "- QDash version: (fill in; the chat does not know it)",
    "",
    "### Hypotheses",
    "(Your own reading, if any. QDash does not diagnose the cause.)",
    "",
    "### Additional context",
    "The error text was left out of this draft because it can contain private details; add",
    "the parts you have checked are safe to share.",
  ].join("\n");
}
