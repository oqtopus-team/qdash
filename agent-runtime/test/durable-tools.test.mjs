import assert from "node:assert/strict";
import { test } from "node:test";

import { Type } from "typebox";

import { buildQDashExtension, decisionMessage } from "../src/durable-tools.ts";

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
  await extension.tools[0].execute({}, { callId: "call-1" }, { abortSignal: undefined });
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
      execute: async (_id, params) => {
        seen.push(params);
        return { content: [], details: {} };
      },
    },
  };
  const { extension } = buildQDashExtension(
    [{ path: "/app/extensions/pi-qcaleval/extensions/qcaleval.ts", tools: new Map([["qcal_evaluate", evaluate]]) }],
    {},
    "/tmp/work",
    connection,
    false,
    ["/app/extensions/pi-qcaleval"],
  );
  const scans = [];
  const api = {
    callId: "call-1",
    conversationId: "conv-1",
    commit: async (change) =>
      change({
        scanEntries: async (query, limit) => {
          scans.push({ query, limit });
          return {
            items: [
              { model: [{ role: "user", content: "evaluate it" }] },
              {
                model: [
                  { role: "toolResult", content: [{ type: "image", data: "png-bytes", mimeType: "image/png" }] },
                ],
              },
            ],
          };
        },
      }),
  };
  const tool = extension.tools[0];

  await tool.execute({ context: "Rabi on Q05" }, api, { abortSignal: undefined });
  assert.deepEqual(scans, [{ query: { conversationId: "conv-1" }, limit: 50 }]);
  assert.deepEqual(seen[0].images, [{ data: "png-bytes", mimeType: "image/png" }]);
  assert.equal(seen[0].context, "Rabi on Q05");

  // Images the model passed itself are kept, and the transcript is not read.
  const own = [{ data: "own-bytes", mimeType: "image/png" }];
  await tool.execute({ context: "Rabi on Q05", images: own }, api, { abortSignal: undefined });
  assert.equal(scans.length, 1);
  assert.deepEqual(seen[1].images, own);
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
