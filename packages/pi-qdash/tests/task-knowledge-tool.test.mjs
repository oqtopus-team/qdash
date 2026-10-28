import assert from "node:assert/strict";
import test from "node:test";

import { registerTaskKnowledgeTool, similarTaskNames, taskKnowledgeSummary, withoutInlineImages } from "../.test-dist/tools/task-knowledge.js";

function registeredTool(client) {
  const tools = new Map();
  registerTaskKnowledgeTool({ registerTool(tool) { tools.set(tool.name, tool); } }, {
    async makeClient() { return client; },
  });
  return tools.get("qdash_get_task_knowledge");
}

test("task knowledge tool defaults to markdown", async () => {
  const calls = [];
  const tool = registeredTool({
    async getTaskKnowledgeMarkdown(name) { calls.push(name); return `# ${name}\nKnowledge`; },
  });
  const result = await tool.execute("test", { taskName: "CheckRabi" });
  assert.deepEqual(calls, ["CheckRabi"]);
  assert.equal(result.content[0].text, "# CheckRabi\nKnowledge");
  assert.equal(result.details.found, true);
  assert.equal(result.details.format, "markdown");
});

test("summary format selects concise interpretation fields", async () => {
  const tool = registeredTool({
    async getTaskKnowledge(name) {
      return {
        name,
        summary: "Rabi calibration.",
        what_it_measures: "Driven oscillation rate.",
        expected_result: { description: "A fitted oscillation.", good_visual: "Clean sinusoid." },
        failure_modes: [{ description: "No oscillation", cause: "Weak drive", next_action: "Inspect Chevron" }],
        check_questions: ["Is the fit stable?"],
      };
    },
  });
  const result = await tool.execute("test", { taskName: "CheckRabi", format: "summary" });
  assert.match(result.content[0].text, /## What it measures/);
  assert.match(result.content[0].text, /Clean sinusoid/);
  assert.match(result.content[0].text, /Next: Inspect Chevron/);
  assert.doesNotMatch(result.content[0].text, /physical_principle/);
});

test("unknown task is non-fatal and suggests matching names", async () => {
  const tool = registeredTool({
    async getTaskKnowledgeMarkdown() { const error = new Error("404 Not Found"); error.status = 404; throw error; },
    async listTaskKnowledge() { return { items: [{ name: "CheckRabi" }, { name: "CheckRamsey" }, { name: "CreateZX90" }] }; },
  });
  const result = await tool.execute("test", { taskName: "CheckRa" });
  assert.equal(result.details.found, false);
  assert.deepEqual(result.details.data.suggestions, ["CheckRabi", "CheckRamsey"]);
  assert.match(result.content[0].text, /No task knowledge found/);
});

test("task knowledge helpers format summaries and rank prefix matches", () => {
  assert.deepEqual(similarTaskNames("rabi", ["CheckRabi", "RabiScan", "Ramsey"]), ["RabiScan", "CheckRabi"]);
  assert.match(taskKnowledgeSummary({ name: "Task", expected_result: {}, failure_modes: [] }), /Not documented/);
});

test("inline figures are dropped from the markdown the model reads", async () => {
  const image = `data:image/png;base64,${"iVBORw0KGgo".repeat(4000)}`;
  const tool = registeredTool({
    async getTaskKnowledgeMarkdown() { return `# CheckRabi\n\n![Rabi oscillation](${image})\n\nAxes: time, P(1)`; },
  });
  const result = await tool.execute("test", { taskName: "CheckRabi" });
  assert.equal(result.content[0].text, "# CheckRabi\n\n![Rabi oscillation](figure omitted: shown on the task's Knowledge page)\n\nAxes: time, P(1)");
  assert.ok(result.content[0].text.length < 200);
  assert.equal(withoutInlineImages("plain ![a](https://x/y.png)"), "plain ![a](https://x/y.png)");
});
