import { readFileSync } from "node:fs";

import { stripFrontmatter } from "@earendil-works/pi-coding-agent";
import { defineTool } from "@earendil-works/pi-durable";
import { Type } from "typebox";

/** A pi skill as the runtime offers it to the model. */
export interface SkillSummary {
  name: string;
  description: string;
  filePath: string;
}

/**
 * Lets the model read the skills bundled with pi-qdash.
 *
 * Pi normally lists skills in its system prompt and the model opens one with
 * its `read` tool. This runtime replaces that prompt and has no file tools, so
 * without this the procedures in the skills (for example how to scope an agent
 * calibration session) never reach the model.
 */
export function buildSkillTool(skills: readonly SkillSummary[]) {
  const byName = new Map(skills.map((skill) => [skill.name, skill]));
  return defineTool({
    name: "read_skill",
    description:
      "Read the full instructions of one QDash skill listed in the system prompt. " +
      "Read the matching skill before starting the workflow it describes.",
    parameters: Type.Object({
      // `{ type, enum }` rather than a literal union, for vLLM guided decoding.
      name: Type.Unsafe<string>({ type: "string", enum: skills.map((skill) => skill.name) }),
    }),
    replay: "safe",
    execute: async ({ name }) => {
      const skill = byName.get(name);
      if (!skill) throw new Error(`unknown skill: ${name}`);
      return { output: [{ type: "text", text: readFileSync(skill.filePath, "utf8") }] };
    },
  });
}

/** What a chat message starts with to invoke a skill explicitly, as in pi: `/skill:name args`. */
export const SKILL_COMMAND_PREFIX = "/skill:";

/** A skill as the chat composer offers it for `/skill:name`. */
export interface SkillCommand {
  name: string;
  description: string;
}

/** The skills a user may invoke from the chat, by name. */
export function skillCommands(skills: readonly SkillSummary[]): SkillCommand[] {
  return skills
    .map(({ name, description }) => ({ name, description }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * Expand a `/skill:name args` message into the skill's instructions followed
 * by the arguments, the way pi's own sessions expand skill commands.
 *
 * This runtime submits messages to the durable harness directly, so pi's
 * expansion never runs; without this the model would only see the literal
 * command. The block carries no file location because the model has no file
 * tools here. An unknown name, an unreadable skill file, or any other
 * message is returned unchanged.
 */
export function expandSkillCommand(text: string, skills: readonly SkillSummary[]): string {
  const match = /^\/skill:(\S+)(?:\s+([\s\S]*))?$/.exec(text);
  if (!match) return text;
  const skill = skills.find((candidate) => candidate.name === match[1]);
  if (!skill) return text;
  let body: string;
  try {
    body = stripFrontmatter(readFileSync(skill.filePath, "utf8")).trim();
  } catch (error) {
    console.warn(`[agent-runtime] skill ${skill.name} unreadable: ${String(error)}`);
    return text;
  }
  const block = `<skill name="${skill.name}">\n${body}\n</skill>`;
  const args = (match[2] ?? "").trim();
  return args ? `${block}\n\n${args}` : block;
}
