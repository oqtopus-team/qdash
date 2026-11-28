import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { buildSkillTool, expandSkillCommand, skillCommands } from "../src/skill-tool.ts";

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

const withFrontmatter = join(dir, "frontmatter.md");
writeFileSync(
  withFrontmatter,
  "---\nname: qdash-characterization\ndescription: Remeasure properties.\n---\n\n# Characterization\nRun T1.\n",
);
const skills = [
  { name: "qdash-one-qubit-calibration", description: "Calibrate qubits.", filePath },
  { name: "qdash-characterization", description: "Remeasure properties.", filePath: withFrontmatter },
];

test("skillCommands lists names and descriptions only, sorted by name", () => {
  assert.deepEqual(skillCommands(skills), [
    { name: "qdash-characterization", description: "Remeasure properties." },
    { name: "qdash-one-qubit-calibration", description: "Calibrate qubits." },
  ]);
});

test("expandSkillCommand puts the skill's body before the user's arguments", () => {
  assert.equal(
    expandSkillCommand("/skill:qdash-characterization remeasure T1 of Q0", skills),
    '<skill name="qdash-characterization">\n# Characterization\nRun T1.\n</skill>\n\nremeasure T1 of Q0',
  );
});

test("expandSkillCommand without arguments sends the skill alone", () => {
  assert.equal(
    expandSkillCommand("/skill:qdash-characterization  ", skills),
    '<skill name="qdash-characterization">\n# Characterization\nRun T1.\n</skill>',
  );
});

test("expandSkillCommand keeps multi-line arguments", () => {
  assert.match(
    expandSkillCommand("/skill:qdash-characterization\nQ0\nQ1", skills),
    /<\/skill>\n\nQ0\nQ1$/,
  );
});

test("expandSkillCommand leaves other messages unchanged", () => {
  for (const text of [
    "remeasure T1",
    "/skill:unknown args",
    "please /skill:qdash-characterization",
    "/qdash-characterization",
  ]) {
    assert.equal(expandSkillCommand(text, skills), text);
  }
});

test("expandSkillCommand leaves the message unchanged when the skill file is gone", () => {
  const missing = [{ name: "gone", description: "", filePath: join(dir, "missing.md") }];
  assert.equal(expandSkillCommand("/skill:gone x", missing), "/skill:gone x");
});
