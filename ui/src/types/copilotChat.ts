/** Shared types for every Copilot chat surface (page, sidebar, floating window). */

/** The calibration result a chat is about; its first turn goes to the analyze endpoint. */
export interface AnalysisContext {
  taskName: string;
  chipId: string;
  qid: string;
  executionId: string;
  taskId: string;
}

/** One figure sent with a chat turn, as the Copilot runtime receives it. */
export interface ChatImageAttachment {
  /** Base64 image bytes without a `data:` prefix. */
  data: string;
  mimeType: string;
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

interface ContentBlock {
  type: "text" | "chart" | "ask" | "approval";
  content: string | null;
  chart: {
    data: Record<string, unknown>[];
    layout: Record<string, unknown>;
  } | null;
  ask?: AskRequest;
  approval?: ApprovalRequest;
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

export type TraceStep =
  | { kind: "thinking"; text: string; startedAt: number; endedAt?: number }
  | {
      kind: "tool";
      id: string;
      tool: string;
      label: string;
      args?: unknown;
      status: "running" | "done" | "error";
      startedAt: number;
      endedAt?: number;
      /** QDash figure paths the tool fetched, shown inline in the chat. */
      figures?: string[];
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
}
