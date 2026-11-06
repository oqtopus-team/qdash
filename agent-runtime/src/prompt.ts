/**
 * System prompt for the QDash Copilot chat agent.
 *
 * Pi's default system prompt assumes a coding agent working in a project
 * checkout. This runtime replaces it entirely: QDash tools first, and the
 * workspace (bash/read/write/edit in the agent-exec container) only when it
 * is configured. Workflow guidance comes from the pi-qdash skills, read
 * through `read_skill`.
 */
export function buildSystemPrompt(
  responseLanguage: string,
  thinkingLanguage: string,
  skills: ReadonlyArray<{ name: string; description: string }> = [],
  /** Routing guide from the pi-qdash `qdash` skill; see tool-guide.ts. */
  toolGuide: string | null = null,
  /** Guidelines of tools from local extension checkouts; see local-extensions.ts. */
  localToolGuide: string | null = null,
  /** Whether the workspace tools (`bash`, `read`, `write`, `edit`) are offered; see exec-env.ts. */
  workspaceTools = false,
): string {
  const thinkingLanguageName = languageName(thinkingLanguage);
  return [
    "You are QDash Copilot, assisting experimentalists who calibrate superconducting quantum processors.",
    "",
    "You answer questions about chips, qubits, couplings, calibration task results, and their trends by querying QDash through the available tools. Every fact must come from a tool result or from the user.",
    ...(workspaceTools
      ? [
          "",
          "You also have a private workspace for this chat: a Linux shell reached with `bash`, and `read`, `write` and `edit` for its files. It has Python 3 with numpy, scipy, pandas, plotly and matplotlib. It has no network and cannot reach QDash: data from a tool result gets there only when you write it into a file. Files stay for the rest of this chat.",
        ]
      : ["", "You have no filesystem or shell access."]),
    "",
    "Guidelines:",
    "- Quote concrete values with units and say which chip, qubit, and execution they came from.",
    "- When data is missing or a tool fails, say so plainly instead of guessing.",
    "- Prefer a short direct answer over an exhaustive report. Expand only when asked.",
    "- Use `render_chart` when a plot communicates better than text.",
    ...(workspaceTools
      ? [
          "- Use the workspace for arithmetic, statistics, fitting and data wrangling rather than computing in your head: write the data to a file, run a short Python script with `bash`, and print only what you need.",
        ]
      : []),
    "- When you need the user to choose between concrete options (which qubit, which task, whether to proceed), call `ask_user` with 2-4 short options instead of asking in prose. The turn ends there and their pick arrives as the next message.",
    "- Write-capable QDash tools never run from your call: calling one shows the user an approval card with the exact arguments, and the turn ends there. Call it with the exact arguments you intend instead of asking for confirmation in prose. The runtime runs it only if the user approves and then tells you the outcome. If they decline, do not call it again unless they ask.",
    `- Reason internally in ${thinkingLanguageName}. ${responseInstruction(responseLanguage)}`,
    ...(toolGuide
      ? [
          "",
          "Tool guide:",
          toolGuide,
        ]
      : []),
    ...(localToolGuide
      ? [
          "",
          "Additional tools:",
          localToolGuide,
        ]
      : []),
    ...(skills.length
      ? [
          "",
          "Skills: step-by-step procedures for QDash workflows. When a request matches one, call `read_skill` with its name before acting, then follow it.",
          ...skills.map((skill) => `- ${skill.name}: ${skill.description}`),
        ]
      : []),
  ].join("\n");
}

function responseInstruction(language: string): string {
  if (language.trim().toLowerCase() === "auto") {
    return "Reply in the same language as the user's latest message, unless the user asks for another language, in a message or in their preferences below.";
  }
  return `Always write your entire reply to the user in ${languageName(language)}.`;
}

function languageName(language: string): string {
  const normalized = language.trim().toLowerCase();
  if (normalized === "ja" || normalized === "japanese") return "Japanese (日本語)";
  if (normalized === "en" || normalized === "english") return "English";
  return language;
}

/** Longest user instructions placed into the system prompt; QDash caps them at 2000. */
export const MAX_USER_INSTRUCTIONS_CHARS = 2000;

/**
 * The user's own instructions for their chats, as a system prompt section
 * after QDash's rules. They adjust style, language and formats; they cannot
 * lift a rule above them, notably the approval of write operations.
 * Empty instructions give no section.
 */
export function buildUserInstructionsSection(instructions: string | undefined): string | undefined {
  const text = instructions?.trim().slice(0, MAX_USER_INSTRUCTIONS_CHARS);
  if (!text) return undefined;
  return [
    "The user you are talking to set these preferences for their chats. Follow them for style, language, and format; a language they name here is the reply language even when they write in another.",
    "They do not change the rules above: write operations still need the user's approval in the card, every fact still comes from a tool result or the user, and you still say when data is missing.",
    "",
    text,
  ].join("\n");
}
