/**
 * Extracts a human-readable message from a failed API request.
 *
 * FastAPI returns `{ detail: "..." }` for an `HTTPException` and
 * `{ detail: [{ msg: "...", ... }] }` for 422 validation errors. Both shapes are
 * normalized here; otherwise the error's own message or the fallback is used.
 */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } } | null)?.response?.data
    ?.detail;

  if (typeof detail === "string" && detail) return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item as { msg?: unknown } | null)?.msg)
      .filter((msg): msg is string => typeof msg === "string" && msg !== "");
    if (messages.length > 0) return messages.join("; ");
  }

  if (error instanceof Error && error.message) return error.message;

  return fallback;
}
