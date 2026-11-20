import type { ScriptDiagnostic } from "@/schemas";
import { getApiErrorMessage } from "@/lib/utils/apiError";

/** A failed validation, preview or evaluation, normalized for display. */
export interface MetricRunError {
  /** HTTP status, when the request reached the API. */
  status: number | null;
  message: string;
  /** Script locations the worker reported (422 worker failures). */
  diagnostics: ScriptDiagnostic[];
  /** Script output captured before the failure. */
  log: string;
  /** The evaluation queue was full (429); retrying later usually works. */
  queueFull: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function readDiagnostics(value: unknown): ScriptDiagnostic[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is ScriptDiagnostic => isRecord(item) && typeof item.message === "string",
  );
}

/**
 * Read an API error of the metric script endpoints. Worker failures answer 422 with
 * `detail = {message, diagnostics, log}`; other errors carry a string or a validation list.
 */
export function describeMetricError(error: unknown, fallback: string): MetricRunError {
  const response = (error as { response?: { status?: unknown; data?: { detail?: unknown } } })
    ?.response;
  const status = typeof response?.status === "number" ? response.status : null;
  const detail = response?.data?.detail;
  if (isRecord(detail)) {
    return {
      status,
      message: typeof detail.message === "string" && detail.message ? detail.message : fallback,
      diagnostics: readDiagnostics(detail.diagnostics),
      log: typeof detail.log === "string" ? detail.log : "",
      queueFull: status === 429,
    };
  }
  return {
    status,
    message: getApiErrorMessage(error, fallback),
    diagnostics: [],
    log: "",
    queueFull: status === 429,
  };
}

/** HTTP status of a failed request, or null. */
export function errorStatus(error: unknown): number | null {
  const status = (error as { response?: { status?: unknown } } | null)?.response?.status;
  return typeof status === "number" ? status : null;
}
