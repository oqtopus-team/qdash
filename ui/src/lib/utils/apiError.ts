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

/**
 * With `responseType: "blob"`, error bodies also arrive as a Blob, so parse the
 * JSON body back into `response.data` before reading its `detail`.
 */
export async function parseBlobErrorBody(error: unknown): Promise<unknown> {
  const response = (error as { response?: { data?: unknown } } | null)?.response;
  if (response?.data instanceof Blob) {
    try {
      response.data = JSON.parse(await response.data.text());
    } catch {
      // Keep the original error when the body is not JSON.
    }
  }
  return error;
}
