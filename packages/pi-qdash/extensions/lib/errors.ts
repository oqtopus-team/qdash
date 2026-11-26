/** The message of a thrown value, for tool text: an Error's message, else the value as text. */
export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * The SDK's numeric `statusCode` of a failed request; a `status` field alone does not count.
 * Callers that act on a status (404, 409, ...) only for SDK errors use this.
 */
export function sdkStatusCode(error: unknown): number | undefined {
  const status = (error as { statusCode?: unknown } | null)?.statusCode;
  return typeof status === "number" ? status : undefined;
}

/**
 * The HTTP status of a failed request: the SDK's numeric `statusCode`, else a numeric
 * `status` (fetch-style errors and test doubles).
 */
export function statusCodeOrStatus(error: unknown): number | undefined {
  if (!error || typeof error !== "object") return undefined;
  const value = error as { statusCode?: unknown; status?: unknown };
  return typeof value.statusCode === "number" ? value.statusCode : typeof value.status === "number" ? value.status : undefined;
}
