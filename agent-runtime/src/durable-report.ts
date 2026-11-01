import type { ReportInfo } from "@earendil-works/pi-durable";

function boundedLabel(value: string): string {
  return value.slice(0, 120);
}

/** Log Pi's structural failure details without recording prompts, tool arguments, or credentials. */
export function logDurableReport(storageName: string, error: unknown, info: ReportInfo): void {
  const task = "task" in info ? info.task : undefined;
  console.error(
    `[agent-runtime] durable report ${JSON.stringify({
      type: info.type,
      session: storageName,
      ...(task ? { task: boundedLabel(task.kind), taskId: task.id } : {}),
      ...("extension" in info && info.extension
        ? { extension: boundedLabel(info.extension) }
        : {}),
      ...("reason" in info ? { reason: info.reason } : {}),
      ...("callback" in info ? { callback: info.callback } : {}),
      errorType: error instanceof Error ? boundedLabel(error.name) : typeof error,
    })}`,
  );
}
