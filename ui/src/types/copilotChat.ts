/** Shared types for every Copilot chat surface (page, sidebar, floating window). */

import type { UiBlockPayload } from "@/lib/copilotUiSpec";

/** The task result a chat is about; its first turn opens with the result's context and figures. */
export interface TaskChatContext {
  taskName: string;
  chipId: string;
  qid: string;
  executionId: string;
  taskId: string;
}

/**
 * A failed execution, or one task of it, that a chat investigates. The API
 * loads the logs itself; this only names the failure. Everything but the
 * execution is optional: an execution can fail before any task result exists.
 */
export interface InvestigationTarget {
  executionId: string;
  taskId?: string | null;
  taskName?: string | null;
  qid?: string | null;
  chipId?: string | null;
}

/** One figure sent with a chat turn, as the Copilot runtime receives it. */
export interface ChatImageAttachment {
  /** Base64 image bytes without a `data:` prefix. */
  data: string;
  mimeType: string;
}

/** Where a user message sent while an answer was written landed in the conversation. */
export interface ChatMessageSteer {
  requestId: string;
  /** Its entry in the runtime's transcript. */
  entryId: string | null;
  /**
   * `exact`: the chat saw where it landed. `approximate`: it was confirmed after the
   * answer it interrupted was saved as one message, and follows that message.
   */
  placement: "exact" | "approximate";
}

export interface ChatMessage {
  role: "user" | "assistant";
  /** Plain text, or a JSON-encoded `CopilotBlocksResult` for assistant answers. */
  content: string;
  /** The message went out with figures attached: the task's result figures or the user's own. */
  attachedImage?: boolean;
  /**
   * Thumbnails (data URLs) of the user's own attachments. Kept only for the
   * browser session that sent them; the server stores presence, not bytes.
   */
  attachments?: string[];
  /** Set on a user message sent while an answer was written (a steer). */
  steer?: ChatMessageSteer;
  /**
   * An assistant answer's entry in the runtime's transcript, from the stream's
   * result. Only such an answer can be branched from; older answers have none.
   */
  entryId?: string;
}

/** Where a branched chat came from. */
export interface ChatBranchOrigin {
  sourceSessionId: string;
  sourceEntryId: string;
}

/** A choice the assistant asks the user to make, shown as buttons. */
export interface AskRequest {
  question: string;
  options: { label: string; description?: string }[];
}

/** A write operation waiting for the user's approval, with the exact arguments it will run with. */
export interface ApprovalRequest {
  id: string;
  tool: string;
  label: string;
  args: Record<string, unknown>;
}

/**
 * A change the assistant proposes to the code open in an editor (the Workflow editor, the
 * metric script editor, or a dashboard's draft as JSON); the user applies it there.
 */
export interface EditProposal {
  summary: string;
  /** The complete new file. */
  code: string;
  /** Which editor the change is for. Absent on proposals made for flows before scripts existed. */
  target?: "flow" | "metric_script" | "dashboard";
  /** The flow's name; for a metric script or a dashboard, set to its name. */
  flowName: string;
  chipId: string | null;
  /** The metric script the change is for (target `metric_script`). */
  scriptId?: string;
  /** The metric script's name (target `metric_script`). */
  scriptName?: string;
  /** The dashboard the change is for (target `dashboard`); null for a new dashboard. */
  dashboardId?: string | null;
  pagePath: string;
}

/** The flow open in the Workflow editor, read when a turn is sent. */
interface FlowEditorContext {
  name: string;
  chipId?: string;
  /** The editor's current text, unsaved changes included. */
  code: string;
  dirty: boolean;
}

/** The metric script open in its editor, read when a turn is sent. */
export interface MetricScriptEditorContext {
  scriptId: string;
  name: string;
  /** The editor's current text, unsaved changes included. */
  code: string;
  dirty?: boolean;
}

/**
 * A dashboard the user may edit, read when a turn is sent. Its unsaved draft is the
 * "code" of the dashboard: JSON with the panels, plus name, description, chip and template
 * for a new dashboard that is not created yet.
 */
interface DashboardEditorContext {
  /** Absent for a new dashboard that exists only as a draft. */
  dashboardId?: string;
  name: string;
  description?: string;
  visibility?: "private" | "project";
  /** The chip the page shows now. */
  chipId?: string | null;
  /** The stored version the draft is based on. */
  version?: number | null;
  /** The draft as JSON (see `dashboardDraft.ts`), unsaved changes included. */
  code: string;
  dirty?: boolean;
}

/** What the user has open while chatting from the sidebar or floating window; sent with every turn. */
export interface PageContext {
  path: string;
  title: string;
  flow?: FlowEditorContext;
  metricScript?: MetricScriptEditorContext;
  dashboard?: DashboardEditorContext;
}

export interface ContentBlock {
  type: "text" | "chart" | "ui" | "ask" | "approval" | "edit";
  /** Markdown for `text`; for `ui`, the block's plain-text fallback. */
  content: string | null;
  chart: {
    data: Record<string, unknown>[];
    layout: Record<string, unknown>;
  } | null;
  ask?: AskRequest;
  approval?: ApprovalRequest;
  edit?: EditProposal;
  /**
   * A read-only UI the assistant composed (`render_ui`). Validated again
   * before rendering; an unknown version or invalid spec shows `ui.fallback`.
   */
  ui?: UiBlockPayload;
}

export interface BlocksResult {
  blocks: ContentBlock[];
  assessment: "good" | "warning" | "bad" | null;
  images_sent?: {
    experiment_figure: boolean;
    experiment_figure_paths: string[];
    expected_images: { alt_text: string; index: number }[];
    task_name: string;
  };
}

/** What an evaluation tool sent its model, shown in the trace on request. */
export interface ToolEvaluation {
  /** The exact prompt: the host's reference, the planner's context, the question. */
  prompt: string;
  /** `provider/modelId` of the judging model. */
  model?: string;
  /** No calibration VLM was configured; the conversation's model judged instead. */
  fallback?: boolean;
  /** The run the evaluation was recorded under, when the figure belonged to a task result. */
  runId?: string;
  evaluationId?: string;
}

/**
 * What the classifier model decided for a `classify` call: the assistant asked
 * it to pick one of the categories it defined. Never the classifier's input.
 */
export interface ToolClassification {
  /** `provider/model` of the classifier model (classifier.yaml). */
  classifier: string;
  /** `classified`: a clear answer; `ambiguous`: no clear winner; `failed`: no answer. */
  outcome: "classified" | "ambiguous" | "failed";
  /** The chosen category, as the assistant named it. */
  category?: string;
  /** The chosen category's probability. */
  probability?: number;
  /** Its lead over the runner-up. */
  margin?: number;
  /** Every category's probability, highest first. */
  probabilities?: { category: string; probability: number }[];
  /** Why there is no answer, when `failed`. */
  reason?: string;
}

export type TraceStep =
  | { kind: "thinking"; text: string; startedAt: number; endedAt?: number }
  | {
      kind: "tool";
      id: string;
      tool: string;
      label: string;
      args?: unknown;
      /**
       * `drafting`: the model is still writing the call; `draft` holds what it has typed.
       * `cancelled`: the turn ended before the call was made; nothing ran.
       */
      status: "drafting" | "running" | "done" | "error" | "cancelled";
      startedAt: number;
      endedAt?: number;
      /** Arguments written so far, by JSON path such as `content` or `path` (while drafting). */
      draft?: Record<string, string>;
      /** The call's index in the model's message, which argument deltas name (while drafting). */
      draftIndex?: number;
      /** What a workspace tool (bash, read, write, edit) answered; the tail when long. */
      output?: string;
      /** A command's exit status (bash). */
      exitCode?: number;
      /** QDash figure paths the tool fetched, shown inline in the chat. */
      figures?: string[];
      /** What an evaluation tool sent its model (qcal_evaluate). */
      evaluation?: ToolEvaluation;
      /** What the classifier decided (classify). */
      classification?: ToolClassification;
    }
  | { kind: "text"; text: string };

/** The work behind an answer, persisted with it so the steps survive a reload. */
export interface ChatTrace {
  steps: TraceStep[];
  durationMs: number;
}

/** Assistant payload stored in `ChatMessage.content` as JSON. */
export type AnswerFeedback = "up" | "down";

export type CopilotBlocksResult = BlocksResult & {
  trace?: ChatTrace;
  /** The user stopped the turn; the blocks hold whatever had streamed. */
  stopped?: boolean;
  /** The user's rating of this answer, kept with it for later evaluation. */
  feedback?: AnswerFeedback;
};

/** The turn that is still streaming. */
export interface LiveTurn {
  steps: TraceStep[];
  startedAt: number;
  /** UI blocks finished so far (`render_ui`), shown live and kept if the user stops. */
  blocks?: ContentBlock[];
}
