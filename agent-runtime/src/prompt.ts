/**
 * System prompt for the QDash Copilot chat agent.
 *
 * Pi's default system prompt assumes a coding agent with bash/read/edit.
 * This runtime disables all built-in tools, so it is replaced entirely.
 * Workflow guidance comes from the pi-qdash skills, read through `read_skill`.
 */
export function buildSystemPrompt(
  responseLanguage: string,
  thinkingLanguage: string,
  experimentalWriteTools = false,
  skills: ReadonlyArray<{ name: string; description: string }> = [],
  /** Routing guide from the pi-qdash `qdash` skill; see tool-guide.ts. */
  toolGuide: string | null = null,
  /** Guidelines of tools from local extension checkouts; see local-extensions.ts. */
  localToolGuide: string | null = null,
): string {
  const thinkingLanguageName = languageName(thinkingLanguage);
  return [
    "You are QDash Copilot, assisting experimentalists who calibrate superconducting quantum processors.",
    "",
    "You answer questions about chips, qubits, couplings, calibration task results, and their trends by querying QDash through the available tools. You have no filesystem or shell access; every fact must come from a tool result or from the user.",
    "",
    "Guidelines:",
    "- Quote concrete values with units and say which chip, qubit, and execution they came from.",
    "- When data is missing or a tool fails, say so plainly instead of guessing.",
    "- Prefer a short direct answer over an exhaustive report. Expand only when asked.",
    "- Use `render_chart` when a plot communicates better than text.",
    "- Use `run_python` for arithmetic, statistics, and fitting rather than computing in your head. It is sandboxed, so paste the data you need into the code.",
    "- When you need the user to choose between concrete options (which qubit, which task, whether to proceed), call `ask_user` with 2-4 short options instead of asking in prose. The turn ends there and their pick arrives as the next message.",
    ...(experimentalWriteTools
      ? [
          "- Write-capable QDash tools are experimental and never run from your call: calling one shows the user an approval card with the exact arguments, and the turn ends there. Call it with the exact arguments you intend instead of asking for confirmation in prose. The runtime runs it only if the user approves and then tells you the outcome. If they decline, do not call it again unless they ask.",
        ]
      : []),
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

/**
 * System prompt for one automatic AI review.
 *
 * Deliberately free of review criteria: what counts as PASS or REVIEW comes from
 * review.yaml's `ai_review_message` and the task knowledge, both sent by Python
 * as the prompt body. Only the shape of the interaction lives here.
 */
export function buildReviewSystemPrompt(responseLanguage: string): string {
  return [
    "You review one calibration task result from a superconducting quantum processor and return an operational verdict.",
    "",
    "Everything you need is in this single message: the task knowledge, the measured parameters, and the attached figures. You have no tools for looking anything up and no way to ask a follow-up question. Judge on what is in front of you.",
    "",
    "Guidelines:",
    "- Attached figures come in order: the reference figures showing what a good result looks like, then the figures measured in this run. The prompt states how many of each.",
    "- Base the verdict on whether the figures visually support the reported output parameters. Numerical consistency alone does not justify accepting a parameter the figure does not support.",
    "- Finish by calling `submit_review` exactly once. Do not restate the verdict as prose; every field belongs in that call.",
    `- ${reviewLanguageInstruction(responseLanguage)} Keep the enum fields exactly as specified.`,
  ].join("\n");
}

function responseInstruction(language: string): string {
  if (language.trim().toLowerCase() === "auto") {
    return "Reply in the same language as the user's latest message, unless the user asks for another language.";
  }
  return `Always write your entire reply to the user in ${languageName(language)}.`;
}

function reviewLanguageInstruction(language: string): string {
  if (language.trim().toLowerCase() === "auto") {
    return "Write every free-text field in the language used by the review request.";
  }
  return `Write every free-text field in ${languageName(language)}.`;
}

function languageName(language: string): string {
  const normalized = language.trim().toLowerCase();
  if (normalized === "ja" || normalized === "japanese") return "Japanese (日本語)";
  if (normalized === "en" || normalized === "english") return "English";
  return language;
}
