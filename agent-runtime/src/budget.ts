/**
 * Time and context budgets for one chat turn.
 *
 * Local models think slowly and, left alone, keep calling tools until the turn
 * runs out of time or context. These keep a turn heading toward an answer.
 */

/** Sent as a steer once a turn has run long, so the model answers with what it has. */
export const WRAP_UP_MESSAGE = [
  "[QDash runtime] This turn is running long.",
  "Do not call any more tools.",
  "Answer the user now from the information you already have,",
  "and say briefly what you could not verify.",
].join(" ");

export interface CompactionBudget {
  reserveTokens: number;
  keepRecentTokens: number;
  backgroundTokens: number;
}

/**
 * How far pi's character-based token estimate (4 chars per token) falls short
 * of what the provider counts. Tool schemas and numeric JSON tokenize nearer 3
 * chars per token, CJK text nearer 1, and an image is a flat 1200 tokens
 * whatever its size. A qwen session that pi estimated below its threshold was
 * counted at 53k tokens by vLLM.
 */
export const ESTIMATE_UNDERCOUNT = 1.5;

/**
 * Compaction thresholds for one model.
 *
 * Pi compacts once the estimated prompt passes `contextWindow - reserveTokens`,
 * and the request then asks for `maxTokens` more. The thresholds are expressed
 * in pi's estimated tokens, so the room the provider actually has
 * (`contextWindow - maxTokens`) is divided by `ESTIMATE_UNDERCOUNT` before it is
 * handed out. The reserve is capped at half the window so small-context models
 * are not compacted on every turn.
 */
export function compactionBudget(contextWindow: number, maxTokens: number): CompactionBudget {
  const estimatedRoom = Math.floor(Math.max(contextWindow - maxTokens, 0) / ESTIMATE_UNDERCOUNT);
  const reserveTokens = Math.min(contextWindow - estimatedRoom, Math.floor(contextWindow / 2));
  // What survives a compaction must leave most of the room for new work.
  const recent = Math.max(Math.floor(estimatedRoom / 4), 1024);
  return {
    reserveTokens,
    keepRecentTokens: Math.min(20_000, recent),
    backgroundTokens: Math.min(32_768, recent),
  };
}
