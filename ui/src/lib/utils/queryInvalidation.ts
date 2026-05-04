import type { Query } from "@tanstack/react-query";

/**
 * Predicate matching all metric / chip / task-result queries — the data that
 * may change when a measurement is excluded, parameters are updated, or
 * calibration history is mutated.
 *
 * orval generates query keys whose first element is the full URL path
 * (e.g. "/metrics/chips/abc/metrics"), so passing `queryKey: ["/metrics"]`
 * to invalidateQueries does not match (TanStack compares array elements
 * strictly, not as substrings) — this predicate substring-matches instead.
 */
export function isChipMetricsQuery(query: Query): boolean {
  const key = query.queryKey[0];
  if (typeof key !== "string") return false;
  return (
    key.startsWith("/metrics/") ||
    key.startsWith("/chip/") ||
    key.startsWith("/chips/") ||
    key.startsWith("/task-results/")
  );
}
