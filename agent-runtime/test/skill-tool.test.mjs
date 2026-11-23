import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { buildSkillTool } from "../src/skill-tool.ts";

const dir = mkdtempSync(join(tmpdir(), "skills-"));
const filePath = join(dir, "SKILL.md");
writeFileSync(filePath, "# Single-qubit calibration\nChoose a template.");
const tool = buildSkillTool([{ name: "qdash-one-qubit-calibration", description: "d", filePath }]);

test("read_skill offers exactly the loaded skill names", () => {
  assert.deepEqual(tool.parameters.properties.name, {
    type: "string",
    enum: ["qdash-one-qubit-calibration"],
  });
});

test("read_skill returns the skill file", async () => {
  const result = await tool.execute({ name: "qdash-one-qubit-calibration" });
  assert.equal(result.output[0].text, "# Single-qubit calibration\nChoose a template.");
});
