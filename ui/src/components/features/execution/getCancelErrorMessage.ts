/**
 * Extracts a human-readable message from a failed execution-cancel request.
 *
 * The API returns error details under `response.data.detail`; this narrows the
 * unknown error to that shape and falls back to a generic message when absent.
 */
export function getCancelErrorMessage(
  error: unknown,
  fallback = "Failed to cancel execution",
): string {
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return detail || fallback;
}
