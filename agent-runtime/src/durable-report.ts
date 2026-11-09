import type { Report } from "@earendil-works/pi-durable";

function boundedLabel(value: string): string {
  return value.slice(0, 120);
}

/**
 * Log Pi's structural failure details without recording prompts, tool arguments, or credentials.
 *
 * The log line keeps its `type` field (the report's `kind`) so existing log searches still match.
 */
export function logDurableReport(storageName: string, report: Report): void {
  const task = "task" in report ? report.task : undefined;
  const { error } = report;
  console.error(
    `[agent-runtime] durable report ${JSON.stringify({
      type: report.kind,
      session: storageName,
      ...(task ? { task: boundedLabel(task.kind), taskId: task.id } : {}),
      ...("extension" in report && report.extension
        ? { extension: boundedLabel(report.extension) }
        : {}),
      ...("reason" in report ? { reason: report.reason } : {}),
      ...("restarts" in report ? { restarts: report.restarts } : {}),
      ...("callback" in report ? { callback: report.callback } : {}),
      errorType: error instanceof Error ? boundedLabel(error.name) : typeof error,
    })}`,
  );
}
