import { describe, expect, it } from "vitest";
import { QDashClient, QDashConfig } from "../src/index.js";

const parent = { calibration_session_id: "cs-1", chip_id: "chip-1", status: "open" };
const pipeline = { chip_id: "chip-1", spec: {}, calibration_session_id: "cs-1", idempotency_key: "key-1" };
const agent = { chip_id: "chip-1", policy: { qids: ["0"], allowed_tasks: ["CheckT1"] }, calibration_session_id: "cs-1" };
function setup(preflight: unknown = parent, result: unknown = {}, status = 200) {
  const calls: Request[] = [];
  const client = new QDashClient(new QDashConfig({ baseUrl: "http://qdash.test", apiToken: "token", projectId: "p1" }), {
    fetch: async (input, init) => {
      const request = new Request(input, init);
      calls.push(request);
      return new Response(JSON.stringify(request.method === "GET" ? preflight : result), {
        status: request.method === "GET" ? status : 200,
        headers: { "Content-Type": "application/json" },
      });
    },
  });
  return { client, calls };
}

describe("associated writes against older APIs", () => {
  for (const kind of ["pipeline", "agent"] as const) {
    const run = (client: QDashClient) => kind === "pipeline"
      ? client.api.executeCalibrationPipeline(pipeline)
      : client.api.createAgentSession(agent);
    it(`${kind} never dispatches when the old API has no parent route`, async () => {
      const { client, calls } = setup({ detail: "Not Found" }, {}, 404);
      await expect(run(client)).rejects.toThrow();
      expect(calls.map((r) => r.method)).toEqual(["GET"]);
    });
    for (const bad of [{}, { ...parent, calibration_session_id: "other" }, { ...parent, chip_id: "other" }]) {
      it(`${kind} refuses an invalid preflight before writing: ${JSON.stringify(bad)}`, async () => {
        const { client, calls } = setup(bad);
        await expect(run(client)).rejects.toThrow(/nothing dispatched/);
        expect(calls.map((r) => r.method)).toEqual(["GET"]);
      });
    }
    for (const bad of [{}, { calibration_session_id: "other", pipeline_run_id: "r1", calibration_admission: "admitted" },
      { calibration_session_id: "cs-1", pipeline_run_id: "", calibration_admission: "pending" }]) {
      it(`${kind} treats a lost association as unknown, never retries: ${JSON.stringify(bad)}`, async () => {
        const { client, calls } = setup(parent, bad);
        await expect(run(client)).rejects.toThrow(/result unknown.*Do not retry automatically/);
        expect(calls.map((r) => r.method)).toEqual(["GET", "POST"]);
      });
    }
  }
  it("allows the server to replay a pipeline recorded in a closed parent", async () => {
    const result = { calibration_session_id: "cs-1", pipeline_run_id: "r1", replayed: true };
    const { client, calls } = setup({ ...parent, status: "closed" }, result);
    await expect(client.api.executeCalibrationPipeline(pipeline)).resolves.toEqual(result);
    expect(calls).toHaveLength(2);
    expect(calls.every((r) => r.headers.get("X-Project-Id") === "p1")).toBe(true);
  });
  it("guards the handwritten agent convenience method too", async () => {
    const result = { calibration_session_id: "cs-1", calibration_admission: "admitted" };
    const { client, calls } = setup(parent, result);
    await expect(client.createAgentSession({ chipId: agent.chip_id, policy: agent.policy, calibrationSessionId: "cs-1" })).resolves.toEqual(result);
    expect(calls.map((r) => r.method)).toEqual(["GET", "POST"]);
  });
  it("keeps unassociated legacy writes free of the new preflight", async () => {
    const { client, calls } = setup(undefined, { legacy: true });
    await client.api.executeCalibrationPipeline({ chip_id: "chip-1", spec: {} });
    await client.createAgentSession({ chipId: "chip-1", policy: agent.policy });
    expect(calls.map((r) => r.method)).toEqual(["POST", "POST"]);
  });
  it("returns a run whose decision link the server echoed", async () => {
    const result = { calibration_session_id: "cs-1", pipeline_run_id: "r1", decision_id: "d-1" };
    const { client, calls } = setup(parent, result);
    await expect(client.api.executeCalibrationPipeline({ ...pipeline, decision_id: "d-1" })).resolves.toEqual(result);
    expect(JSON.parse(await calls[1]!.text()).decision_id).toBe("d-1");
  });
  for (const echoed of [undefined, null, "d-2"]) {
    it(`treats a dropped decision link as unknown, never retries: ${String(echoed)}`, async () => {
      const result = { calibration_session_id: "cs-1", pipeline_run_id: "r1", ...(echoed === undefined ? {} : { decision_id: echoed }) };
      const { client, calls } = setup(parent, result);
      await expect(client.api.executeCalibrationPipeline({ ...pipeline, decision_id: "d-1" })).rejects.toThrow(/without its decision d-1.*Do not retry automatically/);
      expect(calls.map((r) => r.method)).toEqual(["GET", "POST"]);
    });
  }
  it("rejects a decision without a calibration session or an empty decision without network access", async () => {
    const { client, calls } = setup();
    for (const request of [{ chip_id: "chip-1", spec: {}, decision_id: "d-1" }, { ...pipeline, decision_id: " " }]) {
      await expect(client.api.executeCalibrationPipeline(request)).rejects.toThrow(TypeError);
    }
    expect(calls).toHaveLength(0);
  });
  it("rejects empty recording arguments without network access", async () => {
    const { client, calls } = setup();
    for (const request of [{ ...pipeline, idempotency_key: " " }, { ...pipeline, calibration_session_id: "" }]) {
      await expect(client.api.executeCalibrationPipeline(request)).rejects.toThrow(TypeError);
    }
    expect(calls).toHaveLength(0);
  });
  it("treats a keyed pipeline an older API ran without recording as unknown", async () => {
    const { client, calls } = setup(undefined, { legacy: true });
    await expect(
      client.api.executeCalibrationPipeline({ chip_id: "chip-1", spec: {}, idempotency_key: "key-1" }),
    ).rejects.toThrow(/result unknown.*Do not retry automatically/);
    expect(calls.map((r) => r.method)).toEqual(["POST"]);
  });
  it("returns a keyed pipeline recorded in an automatic session", async () => {
    const result = { calibration_session_id: "cs-auto-1", pipeline_run_id: "r1" };
    const { client } = setup(undefined, result);
    await expect(
      client.api.executeCalibrationPipeline({ chip_id: "chip-1", spec: {}, idempotency_key: "key-1" }),
    ).resolves.toEqual(result);
  });
  it("sends a workflow run's session and key, and refuses an older API's unrecorded run", async () => {
    const recorded = { execution_id: "e1", calibration_session_id: "cs-1", calibration_run_id: "r1" };
    const { client, calls } = setup(undefined, recorded);
    await expect(client.executeFlow("demo", {}, { calibrationSessionId: "cs-1", idempotencyKey: "k" })).resolves.toEqual(recorded);
    expect(JSON.parse(await calls[0]!.text())).toEqual({ parameters: {}, calibration_session_id: "cs-1", idempotency_key: "k" });
    const legacy = setup(undefined, { execution_id: "e1" });
    await expect(legacy.client.executeFlow("demo", {}, { idempotencyKey: "k" })).rejects.toThrow(/Workflow result unknown/);
    await expect(legacy.client.executeFlow("demo", {}, { idempotencyKey: " " })).rejects.toThrow(TypeError);
  });
  it("reports a chipless workflow the server refused before launch once, never retrying without its key", async () => {
    const detail = "chipless names no chip (no chip_id parameter and no chip saved with the flow). Nothing was started.";
    const calls: Request[] = [];
    const client = new QDashClient(new QDashConfig({ baseUrl: "http://qdash.test", apiToken: "token", projectId: "p1" }), {
      fetch: async (input, init) => {
        const request = new Request(input, init);
        calls.push(request);
        return new Response(JSON.stringify({ detail }), { status: 400, headers: { "Content-Type": "application/json" } });
      },
    });
    await expect(client.executeFlow("chipless", {}, { idempotencyKey: "k" })).rejects.toThrow(/Nothing was started/);
    expect(calls).toHaveLength(1);
    expect(JSON.parse(await calls[0]!.text())).toEqual({ parameters: {}, idempotency_key: "k" });
  });
});
