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
  it("rejects incomplete or empty recording arguments without network access", async () => {
    const { client, calls } = setup();
    for (const request of [{ ...pipeline, idempotency_key: undefined }, { ...pipeline, idempotency_key: " " }, { ...pipeline, calibration_session_id: "" }]) {
      await expect(client.api.executeCalibrationPipeline(request)).rejects.toThrow(TypeError);
    }
    expect(calls).toHaveLength(0);
  });
});
