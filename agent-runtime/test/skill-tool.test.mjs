import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { buildSkillTool } from "../src/skill-tool.ts";

const dir = mkdtempSync(join(tmpdir(), "skills-"));
const filePath = join(dir, "SKILL.md");
writeFileSync(filePath, "# Calibration agent\nScope one qubit.");
const tool = buildSkillTool([{ name: "qdash-calibration-agent", description: "d", filePath }]);

test("read_skill offers exactly the loaded skill names", () => {
  assert.deepEqual(tool.parameters.properties.name, {
    type: "string",
    enum: ["qdash-calibration-agent"],
  });
});

test("read_skill returns the skill file", async () => {
  const result = await tool.execute({ name: "qdash-calibration-agent" });
  assert.equal(result.content[0].text, "# Calibration agent\nScope one qubit.");
});
