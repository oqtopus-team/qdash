import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { test } from "node:test";

// Characterizes the HTTP routing of server.ts: which method and exact URL reach
// which handler, the runtime bearer check that precedes any body read, the
// unauthenticated health route, the 404 fallback, and the label and response
// each route's failure maps to. The server runs in its own process with a
// mocked runtime whose methods record calls and can be made to fail.
test("server routes: exact matching, runtime auth, health, fallback, and route errors", { timeout: 60_000 }, () => {
  const script = `
    import assert from "node:assert/strict";
    import { once } from "node:events";
    import { Server } from "node:http";
    import { mock } from "bun:test";
    import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
    import { RequestError } from "../src/http.ts";

    let server;
    const listen = Server.prototype.listen;
    Server.prototype.listen = function () {
      server = this;
      return listen.call(this, 0, "127.0.0.1");
    };
    // Route failures are logged as "[agent-runtime] <label> failed:".
    const failures = [];
    const consoleError = console.error;
    console.error = (...args) => {
      const match = typeof args[0] === "string" && /^\\[agent-runtime\\] (.+) failed:$/.exec(args[0]);
      if (match) failures.push(match[1]);
      else consoleError(...args);
    };

    const calls = [];
    const behavior = { skills: "ok", chatModels: "ok", systemPrompt: "ok" };
    let finishEvaluation;
    mock.module("../src/runtime.ts", () => ({
      BACKGROUND_CONTEXT,
      SharedRuntime: { create: async () => ({
        listToolNames: () => [],
        expandSkillCommand: (message) => message,
        storePath: () => "/nonexistent/server-routes/store.sqlite",
        chatSkills: () => {
          calls.push("chatSkills");
          if (behavior.skills === "throw") throw new Error("skills exploded");
          return [{ name: "s1", description: "d1" }];
        },
        chatModels: async () => {
          calls.push("chatModels");
          if (behavior.chatModels === "reject") throw new Error("models exploded");
          if (behavior.chatModels === "request-error") throw new RequestError(503, "models unavailable");
          return [{ provider: "p", name: "m" }];
        },
        chatSystemPrompt: (instructions) => {
          calls.push(["chatSystemPrompt", instructions]);
          if (behavior.systemPrompt === "throw") throw new Error("prompt exploded");
          return { prompt: "system", instructions: instructions ?? null };
        },
        evaluateTask: async (request) => {
          calls.push(["evaluateTask", request.taskId]);
          await new Promise((resolve) => (finishEvaluation = resolve));
          return { verdict: "ok" };
        },
      }) },
      answerText: async () => "",
      pendingApproval: async () => undefined,
    }));
    process.env.AGENT_RUNTIME_TOKEN = "test-runtime-token";
    delete process.env.AGENT_RUNTIME_TOKEN_FILE;
    await import("../src/server.ts");
    if (!server.listening) await once(server, "listening");
    const base = "http://127.0.0.1:" + server.address().port;
    const AUTH = { Authorization: "Bearer test-runtime-token" };
    const USER = { "x-qdash-token": "user-token", "x-qdash-project-id": "p1" };
    const send = async (method, path, { headers = {}, body } = {}) => {
      const response = await fetch(base + path, { method, headers, ...(body === undefined ? {} : { body }) });
      return { status: response.status, type: response.headers.get("content-type"), text: await response.text() };
    };
    const json = (response) => ({ status: response.status, body: JSON.parse(response.text) });
    const NOT_FOUND = { status: 404, type: null, text: "" };
    const notFound = (response) => assert.deepEqual({ status: response.status, type: response.type, text: response.text }, NOT_FOUND);

    // Every protected route with the label its failure is logged under.
    const bodyRoutes = [
      ["POST", "/evaluate", "evaluate"],
      ["POST", "/evaluation-prompts", "evaluation-prompts"],
      ["POST", "/chat", "request"],
      ["POST", "/system-prompt", "system prompt"],
      ["POST", "/chat/active", "active turn"],
      ["POST", "/chat/steer/status", "steer status"],
      ["POST", "/chat/steer", "steer"],
      ["POST", "/chat/abort", "abort"],
      ["POST", "/chat/branch", "branch"],
      ["DELETE", "/session", "session delete"],
    ];
    const protectedRoutes = [...bodyRoutes.map(([m, p]) => [m, p]), ["GET", "/skills"], ["GET", "/chat-models"]];
    try {
      // Health needs no credential and counts running chats and planner-less evaluations.
      assert.deepEqual(json(await send("GET", "/health")), { status: 200, body: { status: "ok", running: 0, evaluating: 0 } });
      assert.equal((await send("GET", "/health")).type, "application/json");
      assert.deepEqual(json(await send("GET", "/health", { headers: { Authorization: "Bearer wrong" } })), { status: 200, body: { status: "ok", running: 0, evaluating: 0 } });

      // A protected route without the runtime bearer, or with a wrong one, is refused
      // before its body is read: an invalid body still gets 401 and reaches no runtime method.
      for (const [method, path] of protectedRoutes) {
        for (const headers of [{}, { Authorization: "Bearer wrong" }, { Authorization: "test-runtime-token" }, USER]) {
          const response = await send(method, path, { headers, ...(method === "GET" ? {} : { body: "{not json" }) });
          assert.deepEqual(json(response), { status: 401, body: { error: "unauthorized" } }, method + " " + path);
          assert.equal(response.type, "application/json");
        }
      }
      assert.deepEqual(calls, []);
      assert.deepEqual(failures, []);

      // Matching is on the method and the exact URL: a query, a trailing slash, a
      // wrong method, or an unknown path is 404 with no body, with or without credentials.
      for (const headers of [{}, AUTH]) {
        for (const [method, path] of [["GET", "/health"], ...protectedRoutes]) {
          notFound(await send(method, path + "?x=1", { headers }));
          notFound(await send(method, path + "/", { headers }));
          notFound(await send(method === "GET" ? "POST" : "GET", path, { headers }));
        }
        notFound(await send("PUT", "/chat", { headers, body: "{}" }));
        notFound(await send("GET", "/", { headers }));
        notFound(await send("GET", "/unknown", { headers }));
        notFound(await send("GET", "/HEALTH", { headers }));
      }
      assert.deepEqual(calls, []);

      // An invalid body on every body-reading route fails in its handler with a
      // RequestError, mapped to 400 and logged under the route's own label.
      for (const [method, path, label] of bodyRoutes) {
        const before = failures.length;
        assert.deepEqual(json(await send(method, path, { headers: AUTH, body: "{not json" })), { status: 400, body: { error: "request body must be valid JSON" } }, path);
        assert.deepEqual(failures.slice(before), [label], path);
      }
      assert.deepEqual(calls, []);

      // Skills and chat models.
      assert.deepEqual(json(await send("GET", "/skills", { headers: AUTH })), { status: 200, body: { skills: [{ name: "s1", description: "d1" }] } });
      assert.deepEqual(json(await send("GET", "/chat-models", { headers: AUTH })), { status: 200, body: { chat_models: [{ provider: "p", name: "m" }] } });
      behavior.chatModels = "reject";
      assert.deepEqual(json(await send("GET", "/chat-models", { headers: AUTH })), { status: 500, body: { error: "internal server error" } });
      behavior.chatModels = "request-error";
      assert.deepEqual(json(await send("GET", "/chat-models", { headers: AUTH })), { status: 503, body: { error: "models unavailable" } });
      assert.deepEqual(failures.slice(-2), ["chat models", "chat models"]);

      // The system prompt passes string instructions only, and its failure is a route error.
      const prompt = async (body) => json(await send("POST", "/system-prompt", { headers: AUTH, body: JSON.stringify(body) }));
      assert.deepEqual(await prompt({ user_instructions: "be brief" }), { status: 200, body: { prompt: "system", instructions: "be brief" } });
      assert.deepEqual(await prompt({ user_instructions: 3 }), { status: 200, body: { prompt: "system", instructions: null } });
      behavior.systemPrompt = "throw";
      const before = failures.length;
      assert.deepEqual(await prompt({}), { status: 500, body: { error: "internal server error" } });
      assert.deepEqual(failures.slice(before), ["system prompt"]);

      // Handlers reached with credentials keep their own validation responses.
      assert.deepEqual(json(await send("POST", "/evaluate", { headers: AUTH, body: "{}" })), { status: 400, body: { error: "task_id is required" } });
      assert.deepEqual(json(await send("POST", "/evaluate", { headers: AUTH, body: JSON.stringify({ task_id: "t1" }) })), { status: 401, body: { error: "QDash user authentication is required" } });
      assert.deepEqual(json(await send("POST", "/chat", { headers: AUTH, body: "{}" })), { status: 400, body: { error: "owner_id, conversation_id and message are required" } });

      // An evaluation in flight shows in health.
      const evaluation = send("POST", "/evaluate", { headers: { ...AUTH, ...USER }, body: JSON.stringify({ task_id: "t1" }) });
      while (!finishEvaluation) await new Promise((resolve) => setTimeout(resolve, 10));
      assert.deepEqual(json(await send("GET", "/health")), { status: 200, body: { status: "ok", running: 0, evaluating: 1 } });
      finishEvaluation();
      assert.deepEqual(json(await evaluation), { status: 200, body: { verdict: "ok" } });
      assert.deepEqual(json(await send("GET", "/health")), { status: 200, body: { status: "ok", running: 0, evaluating: 0 } });

      // Listing skills is synchronous in the request listener: its failure is not a
      // route error but escapes the listener.
      behavior.skills = "throw";
      const uncaught = [];
      const onUncaught = (error) => uncaught.push(error.message);
      process.on("uncaughtException", onUncaught);
      const failuresBefore = failures.length;
      const response = await send("GET", "/skills", { headers: AUTH });
      process.off("uncaughtException", onUncaught);
      assert.notEqual(response.status, 500);
      assert.deepEqual(uncaught, ["skills exploded"]);
      assert.equal(failures.length, failuresBefore);
      // The server keeps serving.
      assert.equal((await send("GET", "/health")).status, 200);
    } finally {
      server.closeAllConnections();
      await new Promise((resolve) => server.close(resolve));
    }
    console.log("SCENARIO OK");
  `;
  const result = spawnSync("bun", ["--eval", script], {
    cwd: new URL(".", import.meta.url),
    encoding: "utf8",
    timeout: 50_000,
  });
  assert.equal(result.status, 0, `${result.error ?? ""}\n${result.stdout}\n${result.stderr}`);
  assert.match(result.stdout, /SCENARIO OK/);
});
