import { readFileSync } from "node:fs";

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
      return { content: [{ type: "text", text: readFileSync(skill.filePath, "utf8") }] };
    },
  });
}
