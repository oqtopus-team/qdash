import type { Query } from "@tanstack/react-query";

/**
 * Predicate that matches any query whose first key starts with one of the
 * given path prefixes. orval generates query keys whose first element is the
 * full URL path (e.g. "/metrics/chips/abc/metrics"), so passing
 * `queryKey: ["/metrics"]` to invalidateQueries does not match (TanStack
 * compares array elements strictly, not as substrings).
 */
export function matchPathPrefixes(...prefixes: string[]) {
  return (query: Query): boolean => {
    const key = query.queryKey[0];
    if (typeof key !== "string") return false;
    return prefixes.some((p) => key.startsWith(p));
  };
}

/**
 * Predicate matching all metric / chip / task-result queries — the data that
 * may change when a measurement is excluded, parameters are updated, or
 * calibration history is mutated.
 */
export const isChipMetricsQuery = matchPathPrefixes(
  "/metrics/",
  "/chip/",
  "/chips/",
  "/task-results/",
);
