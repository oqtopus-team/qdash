/**
 * The metric-runner container's entrypoint (PID 1).
 *
 * Reads the `METRIC_RUNNER_*` settings, starts the runner (runner.ts) on its
 * Unix socket, logs the memory budget of the configured slots against the
 * container's limit, and stops cleanly on SIGTERM or SIGINT. The container has
 * one job: validate and evaluate metric scripts for the API. It holds no QDash
 * credentials and has no network; see
 * docs/developer-guide/architecture/metric-scripts.md.
 */
import { containerMemoryBudget, metricRunnerOptionsFromEnv, startMetricRunner } from "./runner.ts";

if (import.meta.main) {
  const options = metricRunnerOptionsFromEnv(process.env, process.getuid?.() === 0);
  if (!options.isolateUsers) {
    console.warn("[metric-runner] running metric script jobs as the runner's own user (no per-job isolation)");
  }
  const budget = containerMemoryBudget(options);
  if (budget.fits === false) console.warn(`[metric-runner] ${budget.message}`);
  else console.log(`[metric-runner] ${budget.message}`);
  const runner = await startMetricRunner(options);
  console.log(`[metric-runner] listening on ${runner.socketPath}`);
  const stop = () => {
    void runner.close().then(() => process.exit(0));
  };
  process.on("SIGTERM", stop);
  process.on("SIGINT", stop);
}
