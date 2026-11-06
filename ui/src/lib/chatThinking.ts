/**
 * How much the chat model thinks before it answers, chosen per message.
 *
 * "auto" sends nothing and leaves the configured model's own setting
 * (`reasoning_effort` in chat.yaml) in force; the other levels override it for
 * the turns that follow. The runtime reconfigures the conversation on every
 * turn, so a change applies from the next message on.
 */

export type ChatThinkingLevel = "off" | "low" | "medium" | "high";
export type ChatThinkingChoice = "auto" | ChatThinkingLevel;

export const THINKING_CHOICES: ReadonlyArray<{
  value: ChatThinkingChoice;
  label: string;
  description: string;
}> = [
  { value: "auto", label: "Auto", description: "The model's configured default" },
  { value: "off", label: "Off", description: "Answer directly, fastest" },
  { value: "low", label: "Low", description: "Brief reasoning" },
  { value: "medium", label: "Medium", description: "Balanced" },
  { value: "high", label: "High", description: "Thorough, slowest" },
];

const STORAGE_KEY = "qdash_chat_thinking";

/** QDash's reasoning_effort vocabulary, as the backend maps it onto thinking levels. */
const EFFORT_TO_LEVEL: Record<string, ChatThinkingLevel> = {
  none: "off",
  minimal: "low",
  low: "low",
  medium: "medium",
  high: "high",
};

/** The level a configured `reasoning_effort` amounts to, for labelling "Auto". */
export function levelOfEffort(effort: string | null | undefined): ChatThinkingLevel | null {
  return effort ? (EFFORT_TO_LEVEL[effort.toLowerCase()] ?? null) : null;
}

/** The thinking level to send with a turn; nothing for "auto". */
export function thinkingLevelForRequest(choice: ChatThinkingChoice): ChatThinkingLevel | undefined {
  return choice === "auto" ? undefined : choice;
}

function isThinkingChoice(value: unknown): value is ChatThinkingChoice {
  return THINKING_CHOICES.some((choice) => choice.value === value);
}

export function getStoredThinkingChoice(): ChatThinkingChoice {
  if (typeof window === "undefined") return "auto";
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return isThinkingChoice(value) ? value : "auto";
  } catch {
    return "auto";
  }
}

export function setStoredThinkingChoice(choice: ChatThinkingChoice) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    // Remembering the choice is a convenience; the selection still applies.
  }
}
