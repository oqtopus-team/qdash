/**
 * A stand-in for `pi --mode rpc` that speaks the RPC records the validation
 * driver reads, so the driver's framing and dialog handling are tested
 * without a model. FAKE_PI_MODE selects the behaviour:
 *
 * - `approve`: one reviewed-write call with a confirm dialog, then an answer.
 * - `hang`: accept the prompt and settle only after an `abort` command.
 */

const mode = process.env.FAKE_PI_MODE ?? "approve";
const out = (record) => process.stdout.write(`${JSON.stringify(record)}\n`);
const waiting = new Map();

function onRecord(record) {
  if (record.type === "prompt") {
    out({ id: record.id, type: "response", command: "prompt", success: true, data: { disposition: "started" } });
    if (mode === "approve") void approveFlow();
  } else if (record.type === "extension_ui_response") {
    waiting.get(record.id)?.(record);
  } else if (record.type === "abort") {
    out({ type: "agent_settled", aborted: true });
  }
}

function dialog(id, title) {
  return new Promise((resolve) => {
    waiting.set(id, resolve);
    out({ type: "extension_ui_request", id, method: "confirm", title, message: "qdash_create_agent_session will create or modify data in QDash. Continue?" });
  });
}

async function approveFlow() {
  out({ type: "agent_start" });
  out({ type: "tool_execution_start", toolCallId: "read-1", toolName: "qdash_get_chip", args: { chipId: "agentval-x" } });
  out({ type: "tool_execution_start", toolCallId: "call-1", toolName: "qdash_create_agent_session", args: { chipId: "agentval-x", policy: { qids: ["4"], note: "x".repeat(2000) } } });
  out({ type: "extension_ui_request", id: "notify-1", method: "notify", message: "fire and forget" });
  const answer = await dialog("ui-1", "Approve QDash write operation?");
  out({ type: "tool_execution_end", toolCallId: "read-1", toolName: "qdash_get_chip", result: { content: [{ type: "text", text: "chip" }] }, isError: false });
  out({
    type: "tool_execution_end",
    toolCallId: "call-1",
    toolName: "qdash_create_agent_session",
    result: { content: [{ type: "text", text: answer.confirmed ? "created" : "QDash write operation rejected by user" }] },
    isError: !answer.confirmed,
    durationMs: 12,
  });
  // A line separator inside a JSON string must not split the record.
  out({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "Stored T1 is 25.3 us. Done." }], usage: { totalTokens: 42 } } });
  out({ type: "agent_settled", aborted: false });
}

let buffer = "";
process.stdin.on("data", (chunk) => {
  buffer += chunk.toString();
  let index = buffer.indexOf("\n");
  while (index >= 0) {
    const line = buffer.slice(0, index);
    buffer = buffer.slice(index + 1);
    if (line.trim()) onRecord(JSON.parse(line));
    index = buffer.indexOf("\n");
  }
});
process.stdin.on("end", () => process.exit(0));
