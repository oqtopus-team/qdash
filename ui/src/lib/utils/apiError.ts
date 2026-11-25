/**
 * Extracts a human-readable message from a failed API request.
 *
 * FastAPI returns `{ detail: "..." }` for an `HTTPException` and
 * `{ detail: [{ msg: "...", ... }] }` for 422 validation errors; some endpoints send
 * `{ detail: { message: "...", ... } }` (metric script runs, for example). These shapes
 * are normalized here; otherwise the error's own message or the fallback is used.
 *
 * An unexpected server failure also carries `error_id`, the ID under which the server
 * logged its cause; it is appended so users can quote it when reporting the problem.
 */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  const data = (error as { response?: { data?: { detail?: unknown; error_id?: unknown } } } | null)
    ?.response?.data;
  const detail = data?.detail;

  if (typeof detail === "string" && detail) {
    const errorId = data?.error_id;
    return typeof errorId === "string" && errorId ? `${detail} (Error ID: ${errorId})` : detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item as { msg?: unknown } | null)?.msg)
      .filter((msg): msg is string => typeof msg === "string" && msg !== "");
    if (messages.length > 0) return messages.join("; ");
  }

  const message = (detail as { message?: unknown } | null | undefined)?.message;
  if (typeof message === "string" && message) return message;

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
