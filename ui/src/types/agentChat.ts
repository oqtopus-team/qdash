/** Shared types for every Agent chat surface (page, sidebar, floating window). */

import type { UiBlockPayload } from "@/lib/agentUiSpec";

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

/** One figure sent with a chat turn, as the Agent runtime receives it. */
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
  /** Plain text, or a JSON-encoded `AgentBlocksResult` for assistant answers. */
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
  /**
   * The turn this message belongs to (its request ID). The server records a turn's
   * messages itself; a save of this window's copy cannot replace them.
   */
  turnRequestId?: string;
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
/** A calibration session a chat tool call created: its ID and chip. */
export interface CreatedCalibrationSession {
  calibrationSessionId: string;
  chipId?: string;
}

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

/** Where one research task of a `delegate_research` call stands. */
export type SubagentStatus = "queued" | "running" | "done" | "error" | "cancelled" | "interrupted";

/**
 * One read-only research task the assistant delegated to a subagent, as the
 * runtime reported it: bounded, never the subagent's prompt or tool data.
 */
export interface SubagentTask {
  /** Its position in the call, from 1. */
  id: string;
  title: string;
  /** `interrupted`: the call ended or was cut off before this task did. */
  status: SubagentStatus;
  /** Tool calls the subagent made. */
  toolCalls: number;
  startedAt?: number;
  endedAt?: number;
  /** What it is doing now, while it runs: a tool name, or `thinking`. */
  activity?: string;
  /** Its answer, bounded. */
  result?: string;
  /** Why it gave no answer, bounded. */
  error?: string;
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
      /**
       * Stored as `done` because the call was still running when the turn ended or was
       * saved in progress; whether it finished is unknown.
       */
      interrupted?: boolean;
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
      /**
       * The calibration session a successful `qdash_create_calibration_session` call created, as QDash answered it
       * (the tool's result, relayed by the runtime and the API); never the model's arguments or text.
       */
      calibrationSession?: CreatedCalibrationSession;
      /** The research tasks a `delegate_research` call ran, updated while it runs. */
      subagents?: SubagentTask[];
    }
  | { kind: "text"; text: string };

/** The work behind an answer, persisted with it so the steps survive a reload. */
export interface ChatTrace {
  steps: TraceStep[];
  durationMs: number;
}

/** Assistant payload stored in `ChatMessage.content` as JSON. */
export type AnswerFeedback = "up" | "down";

export type AgentBlocksResult = BlocksResult & {
  trace?: ChatTrace;
  /** The user stopped the turn; the blocks hold whatever had streamed. */
  stopped?: boolean;
  /**
   * Saved by the server while the turn still ran: the answer so far. Replaced by the
   * answer's end once the turn ends.
   */
  in_progress?: boolean;
  /**
   * The answer so far of a turn that no process ran any more when a later turn
   * replaced it (its API process restarted mid-turn): it never ended.
   */
  interrupted?: boolean;
  /** The user's rating of this answer, kept with it for later evaluation. */
  feedback?: AnswerFeedback;
};

/**
 * The health of a streaming turn's connection, kept apart from what the turn does.
 * `live`: the stream is open and its heartbeat arrives. `reconnecting`: the stream
 * dropped or went silent past its heartbeat, and the chat is attaching to the turn
 * again; what the assistant does meanwhile is unknown until it is back.
 */
export interface TurnConnection {
  state: "live" | "reconnecting";
  /** When the turn itself last sent something (text, a step, a status); heartbeats do not count. */
  lastUpdateAt: number;
  /** Attempts to attach again since the stream was last live. */
  attempt: number;
}

/**
 * What a turn was last seen doing, kept short so it can be stored with the turn's pointer
 * (`agentTurnStore.ts`): the tool it ran, with the tool's label, or a phrase such as
 * "Thinking". Never the call's arguments or result.
 */
export interface TurnActivitySnapshot {
  tool: string | null;
  label: string;
}

/**
 * A turn of this tab the chat does not stream now. `restoring`: after a reload or a
 * remount, the chat loads the session and reattaches. `other_project`: the turn was sent
 * from another project; it runs on, and the chat follows it again in that project.
 */
export interface DetachedTurn {
  reason: "restoring" | "other_project";
  requestId: string;
  projectId: string | null;
  startedAt: number;
  /** What the chat last saw the turn do, and when the turn last sent something. */
  activity: TurnActivitySnapshot | null;
  lastUpdateAt: number | null;
}

/**
 * A moment of a turn worth telling the user about, raised once per turn: an answer is
 * ready, it waits for the user's approval, answer, or a proposed change, the turn waits for
 * an expert, or it failed.
 */
export type ChatEventKind = "answer" | "approval" | "question" | "edit" | "expert" | "failed";

export interface ChatTurnEvent {
  kind: ChatEventKind;
  sessionId: string;
  /** The turn's own request ID. */
  requestId: string;
  /** The user and the project the turn belongs to. */
  owner: string | null | undefined;
  projectId: string | null;
  /** The chat's title when the event was raised. */
  chatTitle: string;
  /** A short line from the event, such as the error. */
  detail?: string;
}

/** The turn that is still streaming. */
export interface LiveTurn {
  steps: TraceStep[];
  startedAt: number;
  /** UI blocks finished so far (`render_ui`), shown live and kept if the user stops. */
  blocks?: ContentBlock[];
}
