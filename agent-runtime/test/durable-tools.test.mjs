import assert from "node:assert/strict";
import { test } from "node:test";

import { Type } from "typebox";

import { buildQDashExtension, decisionMessage } from "../src/durable-tools.ts";

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
  );

  assert.deepEqual(extension.tools.map((tool) => tool.name), ["qdash_get_default_chip"]);
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
    true,
  );
  assert.deepEqual(Object.keys(extension.tools[0].parameters.properties), ["title"]);
});

test("decision messages tell the model what happened", () => {
  const approval = { id: "c", tool: "qdash_execute_agent_action", label: "Execute", args: {} };
  assert.match(decisionMessage(approval, { approved: false }), /declined .*It was not run/);
  assert.match(
    decisionMessage(approval, { approved: true, result: '{"execution_status":"queued"}' }),
    /approved .*Result:\n\{"execution_status":"queued"\}/,
  );
  assert.match(decisionMessage(approval, { approved: true, error: "409" }), /failed:\n409/);
});
