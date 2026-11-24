import { QDash } from "@oqtopus-team/qdash-sdk";

const json = (body, status = 200) =>
  new Response(body === undefined ? "null" : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

/**
 * The SDK session a tool builds for `client`, with its HTTP requests answered by the test's
 * fake client methods, so a test written against client calls also covers the SDK's requests.
 * A fake that throws an error with `statusCode` answers with that status and its `payload`;
 * a route the fake does not implement answers 404.
 */
export function sdkOver(client) {
  const api = client.api ?? {};
  const routes = [
    ["GET", /^\/calibration-pipelines\/catalog$/, (_m, url) => api.getCalibrationPipelineCatalog(url.searchParams.has("backend_name") ? { backend_name: url.searchParams.get("backend_name") } : undefined)],
    ["POST", /^\/calibration-pipelines\/validate$/, (_m, _u, body) => api.validateCalibrationPipeline(body)],
    ["POST", /^\/calibration-pipelines\/execute$/, (_m, _u, body) => api.executeCalibrationPipeline(body)],
    ["GET", /^\/calibration-sessions$/, (_m, url) => api.listCalibrationSessions(Object.fromEntries(url.searchParams))],
    ["GET", /^\/calibration-sessions\/([^/]+)$/, ([, id]) => api.getCalibrationSession(id)],
    ["POST", /^\/flows\/([^/]+)\/execute$/, ([, name], _u, body) => client.executeFlow(name, body.parameters, {
      ...(body.calibration_session_id != null ? { calibrationSessionId: body.calibration_session_id } : {}),
      ...(body.idempotency_key != null ? { idempotencyKey: body.idempotency_key } : {}),
    })],
    ["POST", /^\/metric-scripts\/validate$/, (_m, _u, body) => client.validateMetricScript(body.source)],
    ["POST", /^\/metric-scripts$/, (_m, _u, body) => client.createMetricScript(body)],
    ["PATCH", /^\/metric-scripts\/([^/]+)$/, ([, id], _u, body) => client.updateMetricScript(id, body)],
    ["GET", /^\/task-results$/, (_m, url) => client.listTaskResults(Object.fromEntries([...url.searchParams].map(([key, value]) => [key === "chip_id" ? "chipId" : key, key === "limit" ? Number(value) : value])))],
    ["GET", /^\/tasks\/([^/]+)\/result$/, ([, id]) => client.getTaskResult(id)],
    ["GET", /^\/executions\/([^/]+)$/, ([, id]) => client.getExecution(id)],
    ["GET", /^\/chips\/([^/]+)\/qubits\/([^/]+)$/, ([, chip, qid]) => client.getChipQubit(chip, qid)],
    ["GET", /^\/chips\/([^/]+)\/couplings\/([^/]+)$/, ([, chip, coupling]) => client.getChipCoupling(chip, coupling)],
    ["GET", /^\/cooldowns\/([^/]+)$/, ([, id]) => api.getCooldown(id)],
  ];
  const fetch = async (input, init) => {
    const request = new Request(input, init);
    const url = new URL(request.url);
    const path = url.pathname.replace(/^\/api/, "");
    const text = await request.text();
    const body = text ? JSON.parse(text) : undefined;
    for (const [method, pattern, handler] of routes) {
      const match = request.method === method ? pattern.exec(path) : null;
      if (!match) continue;
      const decoded = match.map((part) => (part === undefined ? part : decodeURIComponent(part)));
      try {
        return json(await handler(decoded, url, body));
      } catch (error) {
        if (error instanceof TypeError && /is not a function/.test(error.message)) return json({ detail: `no fake for ${method} ${path}` }, 404);
        if (typeof error?.statusCode === "number") return json(error.payload, error.statusCode);
        throw error;
      }
    }
    return json({ detail: `no fake for ${request.method} ${path}` }, 404);
  };
  return new QDash(
    { baseUrl: "https://qdash.example/api", apiToken: "token", ...(client.config?.projectId ? { projectId: client.config.projectId } : {}), readAttempts: 1 },
    { fetch },
  );
}
