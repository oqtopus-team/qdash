import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { QDashClient } from "@oqtopus-team/qdash-client";
import { Type } from "typebox";

import { toTextToolResult } from "../lib/results.js";

type TaskKnowledgeParams = {
  profile?: string;
  configPath?: string;
  useEnv?: boolean;
  taskName: string;
  format?: "markdown" | "summary";
};

type TaskKnowledge = {
  name: string;
  summary?: string;
  what_it_measures?: string;
  expected_result?: Record<string, unknown>;
  failure_modes?: Array<Record<string, unknown>>;
  check_questions?: string[];
};

type TaskKnowledgeList = { items?: Array<{ name?: string }> } | Array<{ name?: string }>;

export type TaskKnowledgeDependencies = {
  makeClient(params: TaskKnowledgeParams): Promise<QDashClient>;
};

function text(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
}

function bulletLines(items: string[]): string[] {
  return items.length ? items.map((item) => `- ${item}`) : ["- Not documented."];
}

export function taskKnowledgeSummary(knowledge: TaskKnowledge): string {
  const expected = knowledge.expected_result ?? {};
  const expectedLines = [
    text(expected.description),
    text(expected.good_visual) && `Good visual: ${text(expected.good_visual)}`,
    text(expected.typical_range) && `Typical range: ${text(expected.typical_range)}`,
  ].filter((value): value is string => Boolean(value));
  const failureLines = (knowledge.failure_modes ?? []).map((mode) => {
    const description = text(mode.description) ?? "Unspecified failure mode";
    const cause = text(mode.cause);
    const nextAction = text(mode.next_action);
    return [description, cause && `Cause: ${cause}`, nextAction && `Next: ${nextAction}`].filter(Boolean).join(" — ");
  });

  return [
    `# ${knowledge.name}`,
    "",
    ...(text(knowledge.summary) ? [text(knowledge.summary)!, ""] : []),
    "## What it measures",
    "",
    text(knowledge.what_it_measures) ?? "Not documented.",
    "",
    "## Expected result",
    "",
    ...bulletLines(expectedLines),
    "",
    "## Failure modes",
    "",
    ...bulletLines(failureLines),
    "",
    "## Check questions",
    "",
    ...bulletLines((knowledge.check_questions ?? []).filter((item) => Boolean(text(item)))),
  ].join("\n");
}

function knownNames(payload: TaskKnowledgeList): string[] {
  const items = Array.isArray(payload) ? payload : payload.items ?? [];
  return items.map((item) => text(item.name)).filter((name): name is string => Boolean(name));
}

export function similarTaskNames(taskName: string, names: string[], limit = 5): string[] {
  const needle = taskName.toLowerCase();
  return names
    .filter((name) => {
      const candidate = name.toLowerCase();
      return candidate.startsWith(needle) || needle.startsWith(candidate) || candidate.includes(needle) || needle.includes(candidate);
    })
    .sort((a, b) => {
      const aPrefix = a.toLowerCase().startsWith(needle) ? 0 : 1;
      const bPrefix = b.toLowerCase().startsWith(needle) ? 0 : 1;
      return aPrefix - bPrefix || a.length - b.length || a.localeCompare(b);
    })
    .slice(0, limit);
}

function notFound(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const value = error as { status?: unknown; statusCode?: unknown; response?: { status?: unknown }; message?: unknown };
  return value.status === 404 || value.statusCode === 404 || value.response?.status === 404 || /\b404\b|not found/i.test(String(value.message ?? ""));
}

const INLINE_IMAGE = /\(data:image\/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=]+\)/g;

/**
 * The knowledge markdown as the model should read it: QDash inlines the
 * expected-plot figures as base64 data URIs for self-contained rendering, which
 * costs tens of thousands of tokens and tells a text model nothing. The alt
 * text stays; the figure itself is shown on QDash's Knowledge page and by
 * qdash_get_figure for results.
 */
export function withoutInlineImages(markdown: string): string {
  return markdown.replace(INLINE_IMAGE, "(figure omitted: shown on the task's Knowledge page)");
}

export function registerTaskKnowledgeTool(pi: Pick<ExtensionAPI, "registerTool">, deps: TaskKnowledgeDependencies): void {
  pi.registerTool({
    name: "qdash_get_task_knowledge",
    label: "QDash Task Knowledge",
    description: "Get task knowledge when asked how to interpret a result, what curve or outcome is expected, which failure modes apply, or what to try next.",
    promptSnippet: "Read QDash task knowledge before interpreting calibration results",
    promptGuidelines: [
      "Use qdash_get_task_knowledge before interpreting task-specific physics, expected curves, failure modes, or next diagnostic checks.",
      "This tool is read-only and does not execute tasks or change parameters.",
    ],
    parameters: Type.Object({
      profile: Type.Optional(Type.String({ description: "QDash profile name. Defaults to env when QDASH_BASE_URL is set, otherwise 'default'." })),
      configPath: Type.Optional(Type.String({ description: "Optional path to qdash config.ini." })),
      useEnv: Type.Optional(Type.Boolean({ description: "Force QDASH_* environment variables instead of a profile." })),
      taskName: Type.String({ description: "QDash task name, for example CheckRabi." }),
      format: Type.Optional(Type.Union([Type.Literal("markdown"), Type.Literal("summary")], { description: "Output format. Defaults to markdown." })),
    }),
    async execute(_toolCallId, params: TaskKnowledgeParams) {
      const client = await deps.makeClient(params);
      const format = params.format ?? "markdown";
      try {
        const data = format === "summary"
          ? await client.getTaskKnowledge(params.taskName) as unknown as TaskKnowledge
          : await client.getTaskKnowledgeMarkdown(params.taskName);
        const markdown = format === "summary"
          ? taskKnowledgeSummary(data as TaskKnowledge)
          : withoutInlineImages(
              typeof data === "string"
                ? data
                : text((data as { markdown?: unknown })?.markdown) ?? JSON.stringify(data, null, 2),
            );
        return toTextToolResult(markdown, data, { taskName: params.taskName, format, found: true });
      } catch (error) {
        if (!notFound(error)) throw error;
        const listed = await client.listTaskKnowledge() as TaskKnowledgeList;
        const suggestions = similarTaskNames(params.taskName, knownNames(listed));
        const markdown = [
          `No task knowledge found for \`${params.taskName}\`.`,
          ...(suggestions.length ? ["", "Similar known task names:", ...suggestions.map((name) => `- \`${name}\``)] : ["", "No similar known task names were found."]),
        ].join("\n");
        return toTextToolResult(markdown, { taskName: params.taskName, found: false, suggestions }, { taskName: params.taskName, format, found: false });
      }
    },
  });
}
