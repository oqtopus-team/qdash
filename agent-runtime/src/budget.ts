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
 * Compaction thresholds for one model.
 *
 * Pi compacts once the prompt passes `contextWindow - reserveTokens`, and the
 * request then asks for `maxTokens` more. Pi estimates tokens from characters,
 * which undercounts images and CJK text, so a reserve equal to `maxTokens`
 * still lets the provider reject the request. Leave a margin on top, scaled to
 * the window so small-context models are not compacted on every turn.
 */
export function compactionBudget(contextWindow: number, maxTokens: number): CompactionBudget {
  const margin = Math.max(2048, Math.round(contextWindow * 0.1));
  const reserveTokens = Math.min(maxTokens + margin, Math.floor(contextWindow / 2));
  const quarter = Math.floor(contextWindow / 4);
  return {
    reserveTokens,
    keepRecentTokens: Math.min(20_000, quarter),
    backgroundTokens: Math.min(32_768, quarter),
  };
}
