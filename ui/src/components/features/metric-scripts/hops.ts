import type { MetricInfo } from "@/schemas";

/** Pair distances a pair metric may declare. */
const ALL_HOPS: readonly number[] = [1, 2];

/** The declared pair distances of a metric, limited to the ones the API knows. */
export function declaredHops(metric: Pick<MetricInfo, "hops"> | undefined): number[] {
  const declared = (metric?.hops ?? ALL_HOPS).filter((hop) => ALL_HOPS.includes(hop));
  return declared.length > 0 ? declared : [...ALL_HOPS];
}
