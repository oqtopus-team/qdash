/**
 * Conversation compaction sized to the chat's model.
 *
 * Pi durable's built-in summarizer (pi-durable 1.6.0, `harness/compaction.js`)
 * sends the summary request with the conversation's thinking level and caps
 * its output at `min(0.8 * reserveTokens, model.maxTokens)`. Reasoning and the
 * summary share that cap. On a local reasoning model such as qwen with a 64k
 * window and 8k output, the reasoning over a long tool-heavy transcript can
 * spend the whole cap. The request then stops with `length`, and the turn
 * fails with "Compaction failed: Summarization hit the token limit".
 *
 * This `beforeCompact` hook, the documented way to supply a summary, writes
 * the summary itself: thinking off, and one retry with shorter tool output
 * when the output is cut off. The transcript is serialized whole: user and
 * assistant text, earlier summaries included, are never cut or left out;
 * only tool arguments and tool results are bounded per call, as the built-in
 * serializer bounds tool results. When that whole transcript does not fit the
 * model's window with room for the output, no request is sent: the hook logs
 * why and hands the compaction to the built-in summarizer, which may then
 * fail honestly instead of summarizing a partial transcript. The harness
 * still chooses what is summarized and places the summary whole. A summary is
 * kept in the task's durable memo, so a restarted compaction places the same
 * text without asking the model again. When both attempts fail, or the
 * provider returns an error, the hook returns nothing and the built-in
 * summarizer runs once more under the harness's own retry policy.
 */

import type { AssistantMessage, Context as ModelContext, Message, Model, Api } from "@earendil-works/pi-ai";
import type { Context } from "@earendil-works/chord/context";
import { AgentDoc, CompactionTask, defineExtension, hook, type Extension } from "@earendil-works/pi-durable";

export const COMPACTION_EXTENSION = "qdash-compaction";

/** The durable memo of a compaction's summary, per summarized range. */
const SUMMARY_MEMO = "qdash.compaction.summary";

/** Output a summary may use at most, whatever the model allows. */
export const SUMMARY_MAX_OUTPUT_TOKENS = 16_384;
/** Output assumed when the model states no limit, still within its window. */
const DEFAULT_OUTPUT_TOKENS = 8_192;
/** Smallest output cap worth a request: below it a structured summary cannot fit. */
export const SUMMARY_MIN_OUTPUT_TOKENS = 512;
/** Tokens kept free of the request and output, for tokenizer differences and provider framing. */
const CONTEXT_MARGIN_TOKENS = 4_096;
/** Share of the remaining room the request may fill: the estimate is approximate. */
const INPUT_SHARE = 0.85;

/**
 * The attempts of one compaction, in order. The second runs when the first
 * was cut off or wrote no summary, or when the first's transcript does not
 * fit. It cuts tool output shorter and asks for a shorter summary, which
 * makes a second cut-off less likely but does not rule it out; a second
 * failure goes to the built-in summarizer.
 */
export const SUMMARY_ATTEMPTS = [
  { toolResultChars: 2_000, argumentChars: 6_000, targetShare: 0.6 },
  { toolResultChars: 500, argumentChars: 1_500, targetShare: 0.35 },
] as const;

type Attempt = (typeof SUMMARY_ATTEMPTS)[number];

const SYSTEM_PROMPT = [
  "You are a context summarization assistant.",
  "Read a conversation between a user and an AI assistant and write a structured summary in the exact format requested.",
  "Do NOT continue the conversation. Do NOT answer questions in it. Do NOT call tools. Output ONLY the summary.",
].join(" ");

function summaryInstructions(targetTokens: number, instructions: string | undefined): string {
  const lines = [
    "The messages above are a conversation to summarize. Create a structured context checkpoint summary that another LLM will use to continue the work.",
    "If the conversation starts with an earlier summary, keep its information and fold the newer messages into it.",
    "",
    "Use this EXACT format:",
    "",
    "## Goal",
    "## Constraints & Preferences",
    "## Progress",
    "### Done",
    "### In Progress",
    "### Blocked",
    "## Key Decisions",
    "## Next Steps",
    "## Critical Context",
    "",
    "Keep every section short: bullet points, no repetition, no raw tool output.",
    `The whole summary must stay under about ${targetTokens} tokens.`,
    "Quote exactly, in their original language: the user's requirements, and the names and IDs of chips, qubits, tasks, metrics, dashboards, scripts, files, functions and error messages.",
    "Record which writes (saves, edits, calibrations, approvals) already ran and their outcome, so they are not repeated.",
  ];
  if (instructions) lines.push("", `Additional focus: ${instructions}`);
  return lines.join("\n");
}

/**
 * A conservative token count of `text`: pi estimates 4 characters per token,
 * but tool JSON and code tokenize nearer 3, and CJK text nearer 1 per
 * character (see ESTIMATE_UNDERCOUNT in budget.ts).
 */
export function estimateTextTokens(text: string): number {
  let ascii = 0;
  let other = 0;
  for (const char of text) {
    if (char.charCodeAt(0) < 0x80) ascii++;
    else other++;
  }
  return Math.ceil(ascii / 3 + other);
}

function truncate(text: string, maxChars: number): string {
  if (text.length <= maxChars) return text;
  return `${text.slice(0, maxChars)}\n[... ${text.length - maxChars} more characters truncated]`;
}

function contentText(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .flatMap((block: { type?: string; text?: unknown }) =>
      block?.type === "text" && typeof block.text === "string" ? [block.text] : [],
    )
    .join("\n");
}

/**
 * One message as transcript text, or `undefined` when it shows nothing. Like
 * the built-in serializer, thinking is left out; tool arguments and results
 * are cut to the attempt's limits.
 */
function serializeMessage(message: Message, attempt: Attempt): string | undefined {
  if (message.role === "user") {
    const text = contentText(message.content);
    return text ? `[User]: ${text}` : undefined;
  }
  if (message.role === "assistant") {
    const parts: string[] = [];
    const text = message.content.flatMap((c) => (c.type === "text" ? [c.text] : [])).join("\n");
    if (text) parts.push(`[Assistant]: ${text}`);
    const calls = message.content.flatMap((c) =>
      c.type === "toolCall"
        ? [
            `${c.name}(${Object.entries(c.arguments ?? {})
              .map(([key, value]) => `${key}=${truncate(JSON.stringify(value) ?? "", attempt.argumentChars)}`)
              .join(", ")})`,
          ]
        : [],
    );
    if (calls.length) parts.push(`[Assistant tool calls]: ${calls.join("; ")}`);
    return parts.length ? parts.join("\n\n") : undefined;
  }
  if (message.role === "toolResult") {
    const text = contentText(message.content);
    if (!text) return undefined;
    const label = message.isError ? `[Tool error ${message.toolName}]` : `[Tool result ${message.toolName}]`;
    return `${label}: ${truncate(text, attempt.toolResultChars)}`;
  }
  return undefined;
}

/**
 * The whole transcript the summarizer reads. Every message with visible
 * content is kept, in order; user and assistant text is never cut, so the
 * user's requirements, an earlier summary, and recorded write outcomes reach
 * the summarizer whole. Only tool arguments and results are bounded, to the
 * attempt's limits.
 */
export function summarySource(messages: readonly Message[], attempt: Attempt): string {
  return messages.flatMap((message) => serializeMessage(message, attempt) ?? []).join("\n\n");
}

/** The summary request for `source`, and its estimated input tokens. */
export function summaryRequest(
  source: string,
  targetTokens: number,
  instructions: string | undefined,
  timestamp: number,
): { request: ModelContext; tokens: number } {
  const text = `<conversation>\n${source}\n</conversation>\n\n${summaryInstructions(targetTokens, instructions)}`;
  return {
    request: { systemPrompt: SYSTEM_PROMPT, messages: [{ role: "user", content: [{ type: "text", text }], timestamp }] },
    tokens: estimateTextTokens(SYSTEM_PROMPT) + estimateTextTokens(text),
  };
}

export interface SummaryBudget {
  /** The output cap of the request, never above the model's stated limit. */
  maxTokens: number;
  /** Estimated tokens the whole request (system prompt, transcript, instructions) may use. */
  inputTokens: number;
}

/**
 * The output cap and input budget of a summary request on `model`, or the
 * reason there is none. Stated limits are respected strictly: the cap never
 * exceeds `maxTokens`, and output plus input plus a margin stay within
 * `contextWindow`. A model without a stated window, or with too little room,
 * gets no QDash request.
 */
export function summaryBudget(
  model: Pick<Model<Api>, "contextWindow" | "maxTokens">,
): SummaryBudget | { reason: string } {
  if (!(model.contextWindow > 0)) return { reason: "no_context_window" };
  const window = model.contextWindow;
  const modelMax = model.maxTokens > 0 ? model.maxTokens : DEFAULT_OUTPUT_TOKENS;
  const maxTokens = Math.min(modelMax, SUMMARY_MAX_OUTPUT_TOKENS, Math.floor(window / 4));
  if (maxTokens < SUMMARY_MIN_OUTPUT_TOKENS) return { reason: "output_limit_too_small" };
  const inputTokens = Math.floor((window - maxTokens - CONTEXT_MARGIN_TOKENS) * INPUT_SHARE);
  if (inputTokens <= 0) return { reason: "context_window_too_small" };
  return { maxTokens, inputTokens };
}

/** The summary of a clean stop with text and no tool call, as the built-in summarizer accepts it. */
function summaryText(message: AssistantMessage): string | undefined {
  if (message.stopReason !== "stop" || message.content.some((c) => c.type === "toolCall")) return undefined;
  const text = message.content
    .flatMap((c) => (c.type === "text" ? [c.text] : []))
    .join("\n")
    .trim();
  return text || undefined;
}

/** Whether a failed attempt is worth the stricter one: the summary was cut off or never written. */
function retryable(message: AssistantMessage): boolean {
  return message.stopReason === "length" || message.stopReason === "stop" || message.stopReason === "toolUse";
}

export interface CompactionExtensionOptions {
  /** Per-request stream timeout, as the chat's own requests use. */
  timeoutMs?: number;
  /** Where attempt diagnostics go; they hold sizes and stop reasons, never conversation text. */
  log?: (line: string) => void;
}

/** The QDash compaction extension, installed in every chat registry. */
export function buildCompactionExtension(options: CompactionExtensionOptions = {}): Extension {
  const log = options.log ?? ((line: string) => console.warn(line));
  return defineExtension({
    name: COMPACTION_EXTENSION,
    hooks: [
      hook(CompactionTask, {
        beforeCompact: async (compaction, api, context: Context) => {
          const range = `${compaction.entries[0]?.id ?? "start"}-${compaction.firstKept}`;
          const memo = `${SUMMARY_MEMO}:${range}`;
          const stored = await api.memo<string>(memo, context);
          if (stored !== undefined) return { summary: stored };

          const agent = await api.snapshot(AgentDoc, api.conversationId, context);
          const ref = agent?.model;
          const model = ref ? api.models.getModel(ref.provider, ref.modelId) : undefined;
          if (!ref || !model) return undefined;
          const name = `${ref.provider}/${ref.modelId}`;
          const budget = summaryBudget(model);
          if ("reason" in budget) {
            log(`[agent-runtime] compaction summary of ${name} not sent (${budget.reason}); using the built-in summarizer`);
            return undefined;
          }
          const { maxTokens, inputTokens } = budget;

          let sent = 0;
          for (const [index, attempt] of SUMMARY_ATTEMPTS.entries()) {
            const position = `attempt ${index + 1}/${SUMMARY_ATTEMPTS.length} of ${name}`;
            const { request, tokens } = summaryRequest(
              summarySource(compaction.messages, attempt),
              Math.floor(maxTokens * attempt.targetShare),
              compaction.instructions,
              api.now(),
            );
            if (tokens > inputTokens) {
              // The whole transcript does not fit; no part of it is left out to make it fit.
              log(
                `[agent-runtime] compaction summary ${position}: not sent, ` +
                  `request~${tokens}/${inputTokens} tokens does not fit with output ${maxTokens}`,
              );
              continue;
            }
            sent++;
            let message: AssistantMessage;
            try {
              // No `reasoning`: thinking stays off, so the whole cap is the summary's.
              message = await api.models.completeSimple(model, request, {
                maxTokens,
                cacheRetention: "none",
                ...(context.abortSignal ? { signal: context.abortSignal } : {}),
                telemetry: context.telemetry,
                ...(options.timeoutMs ? { timeoutMs: options.timeoutMs } : {}),
              });
            } catch (error) {
              if (context.abortSignal?.aborted) throw error;
              log(`[agent-runtime] compaction summary of ${name} threw; using the built-in summarizer`);
              return undefined;
            }
            // A stop or close: the harness aborts the task and keeps the context as it was.
            context.abortSignal?.throwIfAborted();
            log(
              `[agent-runtime] compaction summary ${position}: ` +
                `stop=${message.stopReason} output=${message.usage?.output ?? "?"}/${maxTokens} ` +
                `request~${tokens}/${inputTokens} tokens`,
            );
            const summary = summaryText(message);
            if (summary !== undefined) return { summary: await api.memo(memo, summary, context) };
            if (!retryable(message)) return undefined;
          }
          if (sent === 0) {
            log(`[agent-runtime] compaction summary of ${name}: whole transcript too large; using the built-in summarizer`);
            return undefined;
          }
          log(`[agent-runtime] compaction summary of ${name} failed; using the built-in summarizer`);
          return undefined;
        },
      }),
    ],
  });
}

/** What the user is told when compaction fails, in place of the provider's error text. */
export const COMPACTION_FAILED_MESSAGE = [
  "This chat has grown too long for the model, and summarizing its earlier part failed.",
  "The stored chat is intact: your messages, approvals and tool results are kept, including any that finished before the failure.",
  "Press Continue to try again; it does not send your message again or rerun finished tool calls.",
  "After a summary, the model sees the earlier part only in summarized form, so restate any detail it misses.",
  "If it keeps failing, start a new chat.",
].join(" ");

/** Whether an unanswered turn failed because its compaction did. */
export function isCompactionFailure(reason: string | undefined, detail: unknown): boolean {
  return reason === "model_error" && typeof detail === "string" && detail.startsWith("Compaction failed:");
}
