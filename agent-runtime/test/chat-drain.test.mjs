import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { test } from "node:test";

// Isolate module mocks so the real runtime remains available to the other tests.
for (const failure of ["watch", "entries"]) {
  test(`chat reports an error instead of done when final ${failure} fails`, () => {
    const script = `
      import assert from "node:assert/strict";
      import { once } from "node:events";
      import { Server } from "node:http";
      import { mock } from "bun:test";
      import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";

      let server;
      const listen = Server.prototype.listen;
      Server.prototype.listen = function () {
        server = this;
        return listen.call(this, 0, "127.0.0.1");
      };
      let watches = 0;
      let closed = false;
      const conversation = {
        context: async () => ({ entries: [] }),
        submit: async () => ({ wait: async () => ({ status: "done", type: "input", answer: 3 }) }),
        watch: async () => {
          watches++;
          if (watches === 2 && ${JSON.stringify(failure)} === "watch") {
            throw new Error("injected drain failure");
          }
          return {
            value: { entries: [], docs: {}, ...(watches === 2 ? { before: 2 } : {}) },
            start: () => {},
            stop: async () => {},
          };
        },
        entries: async () => { throw new Error("injected drain failure"); },
      };
      mock.module("../src/runtime.ts", () => ({
        BACKGROUND_CONTEXT,
        SharedRuntime: { create: async () => ({
          listToolNames: () => [],
          openSession: async () => ({ conversation, close: async () => { closed = true; } }),
        }) },
        answerText: async () => "Answer",
        pendingApproval: async () => undefined,
      }));
      process.env.CHAT_PING_MS = "0";
      process.env.CHAT_TIMEOUT_MS = "0";
      process.env.CHAT_WRAP_UP_MS = "0";
      process.env.AGENT_RUNTIME_TOKEN = "test-runtime-token";
      delete process.env.AGENT_RUNTIME_TOKEN_FILE;
      await import("../src/server.ts");
      if (!server.listening) await once(server, "listening");
      let lines;
      try {
        const response = await fetch("http://127.0.0.1:" + server.address().port + "/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json", "x-qdash-token": "test-token", Authorization: "Bearer test-runtime-token" },
          body: JSON.stringify({ owner_id: "test-owner", conversation_id: "test-conversation", message: "hello" }),
        });
        assert.equal(response.status, 200);
        lines = (await response.text()).trim().split("\\n").map(JSON.parse);
      } finally {
        server.closeAllConnections();
        await new Promise((resolve) => server.close(resolve));
      }
      assert.equal(watches, 2);
      assert.equal(closed, true);
      assert.deepEqual(lines, [{ type: "error", message: "injected drain failure" }]);
    `;
    const result = spawnSync("bun", ["--eval", script], {
      cwd: new URL(".", import.meta.url),
      encoding: "utf8",
      timeout: 30_000,
    });
    assert.equal(result.status, 0, `${result.error ?? ""}\n${result.stdout}\n${result.stderr}`);
  });
}
