import assert from "node:assert/strict";
import { test } from "node:test";

import { Type } from "typebox";

import { boundToolText, buildQDashExtension, decisionMessage, MAX_TOOL_TEXT_CHARS, ToolCancelled, untilAborted } from "../src/durable-tools.ts";

const connection = {
  toolArgs: {
    profile: "runtime",
    configPath: "/private/config.ini",
    useEnv: false,
  },
};

function registered(name) {
  let calls = 0;
  return {
    definition: {
      name,
      label: name,
      description: name,
      parameters: Type.Object({}),
      execute: async () => {
        calls += 1;
        return { content: [], details: {} };
      },
    },
    calls: () => calls,
  };
}

test("only explicitly reviewed pi-qdash tools enter the durable registry", () => {
  const { extension } = buildQDashExtension(
    [
      {
        tools: new Map([
          ["qdash_get_default_chip", registered("qdash_get_default_chip")],
          ["qdash_create_forum_post", registered("qdash_create_forum_post")],
          ["qdash_future_unreviewed_tool", registered("qdash_future_unreviewed_tool")],
        ]),
      },
    ],
    {},
    "/tmp/work",
    connection,
  );

  assert.deepEqual(
    extension.tools.map((tool) => tool.name),
    ["qdash_get_default_chip"],
  );
});

test("local extension checkouts are trusted by path, not by tool name", () => {
  const roots = ["/app/extensions/pi-qcaleval"];
  const readOnly = registered("qcal_evaluate");
  readOnly.definition.annotations = { readOnlyHint: true };
  const pinned = {
    path: "/app/.pi-agent/packages/pi-qdash/extensions/qdash.ts",
    tools: new Map([
      ["qdash_get_default_chip", registered("qdash_get_default_chip")],
      ["qdash_future_unreviewed_tool", registered("qdash_future_unreviewed_tool")],
    ]),
  };
  const local = {
    path: "/app/extensions/pi-qcaleval/extensions/qcaleval.ts",
    tools: new Map([
      ["qcal_evaluate", readOnly],
      ["qcal_store_result", registered("qcal_store_result")],
      // An experimental write name keeps its opt-in even from a checkout.
      ["qdash_create_forum_post", registered("qdash_create_forum_post")],
    ]),
  };
  const { extension } = buildQDashExtension(
    [local, pinned],
    {},
    "/tmp/work",
    connection,
    false,
    roots,
  );
  const byName = new Map(extension.tools.map((tool) => [tool.name, tool]));

  assert.deepEqual(
    [...byName.keys()].sort(),
    ["qcal_evaluate", "qcal_store_result", "qdash_get_default_chip"],
  );
  // Only a tool annotated read-only may rerun after an interruption.
  assert.equal(byName.get("qcal_evaluate").replay, "safe");
  assert.equal(byName.get("qcal_store_result").replay, "unsafe");
  assert.equal(byName.get("qdash_get_default_chip").replay, "safe");
});

test("a checkout tool with a pinned name replaces the pinned implementation", async () => {
  const pinnedTool = registered("qdash_get_default_chip");
  const localTool = registered("qdash_get_default_chip");
  const { extension } = buildQDashExtension(
    [
      { path: "/app/.pi-agent/packages/pi-qdash/extensions/qdash.ts", tools: new Map([["qdash_get_default_chip", pinnedTool]]) },
      { path: "/app/extensions/dev/extensions/dev.ts", tools: new Map([["qdash_get_default_chip", localTool]]) },
    ],
    {},
    "/tmp/work",
    connection,
    false,
    ["/app/extensions/dev"],
  );

  assert.equal(extension.tools.length, 1);
  const result = await extension.tools[0].execute({}, { callId: "call-1" }, { abortSignal: undefined });
  assert.deepEqual(result.output, []);
  assert.equal(localTool.calls(), 1);
  assert.equal(pinnedTool.calls(), 0);
});

test("a checkout tool with an `images` parameter gets the newest transcript figure", async () => {
  const seen = [];
  const evaluate = {
    definition: {
      name: "qcal_evaluate",
      label: "Evaluate",
      description: "Evaluate a plot",
      parameters: Type.Object({
        context: Type.String(),
        images: Type.Optional(Type.Array(Type.Object({ data: Type.String(), mimeType: Type.String() }))),
      }),
      execute: async (_id, params, _signal, _onUpdate, ctx) => {
        seen.push({ ...params, ctxModel: ctx.model });
        return { content: [], details: {} };
      },
    },
  };
  const qwen = { provider: "openai-compatible", id: "qwen3.8-flash-next", input: ["text", "image"] };
  const { extension } = buildQDashExtension(
    [{ path: "/app/extensions/pi-qcaleval/extensions/qcaleval.ts", tools: new Map([["qcal_evaluate", evaluate]]) }],
    { getModel: (provider, id) => (provider === qwen.provider && id === qwen.id ? qwen : undefined) },
    "/tmp/work",
    connection,
    false,
    ["/app/extensions/pi-qcaleval"],
  );
  const scans = [];
  const api = {
    callId: "call-1",
    conversationId: "conv-1",
    // The conversation's model reaches the tool, so it can fall back to it.
    agent: async () => ({ model: { provider: qwen.provider, modelId: qwen.id } }),
    commit: async (change) =>
      change({
        scanEntries: async (query, limit) => {
          scans.push({ query, limit });
          return {
            items: [
              { model: [{ role: "user", content: "evaluate it" }] },
              {
                model: [
                  {
                    role: "toolResult",
                    content: [{ type: "image", data: "png-bytes", mimeType: "image/png" }],
                    details: { tool: "qdash_get_task_figures", taskId: "task-7" },
                  },
                ],
              },
            ],
          };
        },
      }),
  };
  const tool = extension.tools[0];

  const result = await tool.execute({ context: "Rabi on Q05" }, api, { abortSignal: undefined });
  assert.deepEqual(scans, [{ query: { conversationId: "conv-1" }, limit: 50 }]);
  assert.deepEqual(seen[0].images, [{ data: "png-bytes", mimeType: "image/png" }]);
  assert.equal(seen[0].context, "Rabi on Q05");
  assert.equal(seen[0].ctxModel, qwen);
  // The result records what the host put into the call, so a planner turn
  // leaves the same evaluation record as a direct evaluation.
  assert.equal(result.details.host.context, "Rabi on Q05");
  assert.equal(result.details.host.figures.length, 1);
  assert.equal(result.details.host.figures[0].mime_type, "image/png");
  assert.equal(result.details.host.knowledge, null);
  assert.equal(result.details.host.task_id, "task-7");
  assert.ok(result.details.host.duration_ms >= 0);

  // Bytes the model copied into the call are replaced by the transcript's figure:
  // a retyped base64 string is corrupt more often than not.
  const own = [
    {
      data: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
      mimeType: "image/png",
    },
  ];
  await tool.execute({ context: "Rabi on Q05", images: own }, api, { abortSignal: undefined });
  assert.equal(scans.length, 2);
  assert.deepEqual(seen[1].images, [{ data: "png-bytes", mimeType: "image/png" }]);
  // Only when the transcript holds no figure do bytes the model passed survive.
  const noFigures = {
    ...api,
    commit: async (change) =>
      change({ scanEntries: async () => ({ items: [{ model: [{ role: "user", content: "evaluate it" }] }] }) }),
  };
  await tool.execute({ context: "Rabi on Q05", images: own }, noFigures, { abortSignal: undefined });
  assert.deepEqual(seen[2].images, own);

  // `max_images` asks for the last N figures of the newest message that has any.
  const twoFigures = {
    ...api,
    commit: async (change) =>
      change({
        scanEntries: async () => ({
          items: [
            {
              model: [
                {
                  role: "user",
                  content: [
                    { type: "text", text: "review this" },
                    { type: "image", data: "expected", mimeType: "image/png" },
                    { type: "image", data: "measured", mimeType: "image/png" },
                  ],
                },
              ],
            },
          ],
        }),
      }),
  };
  await tool.execute({ context: "CheckRabi", max_images: 2 }, twoFigures, { abortSignal: undefined });
  assert.deepEqual(
    seen[3].images.map((image) => image.data),
    ["expected", "measured"],
  );
  await tool.execute({ context: "CheckRabi" }, twoFigures, { abortSignal: undefined });
  assert.deepEqual(
    seen[4].images.map((image) => image.data),
    ["measured"],
  );
});

test("experimental write tools require opt-in and never run from the model's call", async () => {
  const write = registered("qdash_create_forum_post");
  const { extension, writeTools } = buildQDashExtension(
    [
      {
        tools: new Map([
          ["qdash_get_default_chip", registered("qdash_get_default_chip")],
          ["qdash_create_forum_post", write],
          ["qdash_future_unreviewed_tool", registered("qdash_future_unreviewed_tool")],
        ]),
      },
    ],
    {},
    "/tmp/work",
    connection,
    true,
  );

  assert.deepEqual(
    extension.tools.map((tool) => tool.name),
    ["qdash_get_default_chip", "qdash_create_forum_post"],
  );
  const writeTool = extension.tools.find((tool) => tool.name === "qdash_create_forum_post");
  const context = { abortSignal: new AbortController().signal };

  // Even a model that sets confirmWrite only gets an approval request.
  const requested = await writeTool.execute(
    { title: "T1 drop", confirmWrite: true, profile: "default" },
    { callId: "call-1" },
    context,
  );
  assert.equal(write.calls(), 0);
  assert.match(requested.output[0].text, /Approval requested/);
  assert.deepEqual(requested.control, { terminate: true });
  assert.deepEqual(requested.details.approval, {
    id: "call-1",
    tool: "qdash_create_forum_post",
    label: "qdash_create_forum_post",
    args: { title: "T1 drop" },
  });

  await writeTools.runApproved(requested.details.approval);
  assert.equal(write.calls(), 1);
});

test("the model is not offered the confirmation flag", () => {
  const tool = registered("qdash_create_forum_post");
  tool.definition.parameters = Type.Object({
    title: Type.String(),
    confirmWrite: Type.Optional(Type.Boolean()),
  });
  const { extension } = buildQDashExtension(
    [{ tools: new Map([["qdash_create_forum_post", tool]]) }],
    {},
    "/tmp/work",
    connection,
    true,
  );
  assert.deepEqual(Object.keys(extension.tools[0].parameters.properties), ["title"]);
});

test("decision messages tell the model what happened", () => {
  const approval = {
    id: "c",
    tool: "qdash_execute_agent_action",
    label: "Execute",
    args: {},
  };
  assert.match(decisionMessage(approval, { approved: false }), /declined .*It was not run/);
  assert.match(
    decisionMessage(approval, {
      approved: true,
      result: '{"execution_status":"queued"}',
    }),
    /approved .*Result:\n\{"execution_status":"queued"\}/,
  );
  assert.match(decisionMessage(approval, { approved: true, error: "409" }), /failed:\n409/);
});

test("a trusted installed package gets the checkout treatment", () => {
  const readOnly = registered("qcal_evaluate");
  readOnly.definition.annotations = { readOnlyHint: true };
  const { extension } = buildQDashExtension(
    [
      {
        path: "/app/.pi-agent/npm/node_modules/@orangekame3/pi-qcaleval/extensions/qcaleval.ts",
        tools: new Map([["qcal_evaluate", readOnly]]),
      },
      {
        path: "/app/.pi-agent/npm/node_modules/@someone/pi-other/extensions/other.ts",
        tools: new Map([["other_tool", registered("other_tool")]]),
      },
    ],
    {},
    "/tmp/work",
    connection,
    false,
    [],
    ["@orangekame3/pi-qcaleval"],
  );
  // The listed package is offered; an unlisted installed package still needs the allowlist.
  assert.deepEqual(
    extension.tools.map((tool) => tool.name),
    ["qcal_evaluate"],
  );
  assert.equal(extension.tools[0].replay, "safe");
});

test("a tool's text reaches the model without inline images and within the budget", async () => {
  const image = `data:image/png;base64,${"A".repeat(5000)}`;
  const long = "x".repeat(MAX_TOOL_TEXT_CHARS + 500);
  const tool = registered("qdash_get_task_knowledge");
  tool.definition.execute = async () => ({
    content: [
      { type: "text", text: `# CheckRabi\n![plot](${image})\nAxes: time` },
      { type: "text", text: long },
      { type: "image", data: "ignored", mimeType: "image/png" },
    ],
    details: {},
  });
  const { extension } = buildQDashExtension(
    [{ tools: new Map([["qdash_get_task_knowledge", tool]]) }],
    {},
    "/tmp/work",
    connection,
  );
  const result = await extension.tools[0].execute({}, { callId: "c1" }, { abortSignal: undefined });
  assert.equal(result.output[0].text, "# CheckRabi\n![plot](data:… (inline image omitted; QDash shows it))\nAxes: time");
  assert.ok(result.output[1].text.length < MAX_TOOL_TEXT_CHARS + 200);
  assert.match(result.output[1].text, /output truncated to 24000 characters/);
  assert.deepEqual(result.output[2], { type: "image", data: "ignored", mimeType: "image/png" });
  assert.equal(boundToolText("short", "t"), "short");
});

test("a cancelled turn does not wait for a tool that ignores the signal", async () => {
  const tool = registered("qdash_wait_execution");
  tool.definition.execute = () => new Promise(() => {}); // polls forever, never looks at the signal
  const { extension } = buildQDashExtension(
    [{ tools: new Map([["qdash_wait_execution", tool]]) }],
    {},
    "/tmp/work",
    connection,
  );
  const controller = new AbortController();
  const call = extension.tools[0].execute({}, { callId: "c1" }, { abortSignal: controller.signal });
  setTimeout(() => controller.abort(), 10);
  await assert.rejects(call, (error) => error instanceof ToolCancelled && /keeps running in QDash/.test(error.message));
  await assert.rejects(untilAborted(new Promise(() => {}), controller.signal, "x"), ToolCancelled);
  assert.equal(await untilAborted(Promise.resolve(3), new AbortController().signal, "x"), 3);
});
