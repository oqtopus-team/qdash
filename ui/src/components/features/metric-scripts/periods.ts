import { dateTimeLocalToDate, formatDateTime, toDateTimeLocal } from "@/lib/utils/datetime";

/**
 * The data window a metric is evaluated over, as the API's `RelativePeriod | AbsolutePeriod`
 * with the discriminator always present.
 */
export type MetricPeriod =
  | { kind: "relative"; days: number }
  | { kind: "absolute"; start: string; end: string };

export const DEFAULT_PERIOD_DAYS = 14;
const MINUTES = "yyyy-MM-dd HH:mm";
/**
 * The API rejects longer relative periods and clamps longer history spans. A series metric
 * also refuses a longer fixed range, since the clamped-away bins would chart as gaps.
 */
export const MAX_PERIOD_DAYS = 400;
const DAY_MS = 24 * 60 * 60 * 1000;

export function defaultPeriod(): MetricPeriod {
  return { kind: "relative", days: DEFAULT_PERIOD_DAYS };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** A stored or typed period, normalized; anything unreadable becomes the default. */
export function readPeriod(value: unknown): MetricPeriod {
  if (!isRecord(value)) return defaultPeriod();
  if (value.kind === "absolute") {
    return {
      kind: "absolute",
      start: typeof value.start === "string" ? value.start : "",
      end: typeof value.end === "string" ? value.end : "",
    };
  }
  const days = typeof value.days === "number" && Number.isFinite(value.days) ? value.days : null;
  return { kind: "relative", days: days ?? DEFAULT_PERIOD_DAYS };
}

/**
 * Validation message for a period, or null when the API will accept it. With `series`, a
 * fixed range longer than `MAX_PERIOD_DAYS` is refused as the API refuses it.
 */
export function periodError(
  period: MetricPeriod,
  { series = false }: { series?: boolean } = {},
): string | null {
  if (period.kind === "absolute") {
    const start = Date.parse(period.start);
    const end = Date.parse(period.end);
    if (!period.start || Number.isNaN(start)) return "Enter the period start";
    if (!period.end || Number.isNaN(end)) return "Enter the period end";
    if (end <= start) return "The period must end after it starts";
    if (series && end - start > MAX_PERIOD_DAYS * DAY_MS) {
      const days = Math.ceil((end - start) / DAY_MS);
      return `A time series covers at most ${MAX_PERIOD_DAYS} days; this range spans ${days}. Shorten it or split it into several panels`;
    }
    return null;
  }
  const days = period.days;
  if (!Number.isInteger(days) || days < 1 || days > MAX_PERIOD_DAYS) {
    return `Enter whole days between 1 and ${MAX_PERIOD_DAYS}`;
  }
  return null;
}

/** "Last 14 days", or the fixed window in the UI time zone. */
export function formatPeriod(period: MetricPeriod): string {
  if (period.kind === "absolute") {
    return `${formatDateTime(period.start, MINUTES)} – ${formatDateTime(period.end, MINUTES)}`;
  }
  const days = period.days;
  return days === 1 ? "Last day" : `Last ${days} days`;
}

/** The window an evaluation actually used, as returned by the API. */
export function formatResolvedPeriod(start: string, end: string): string {
  return `${formatDateTime(start, MINUTES)} – ${formatDateTime(end, MINUTES)}`;
}

/** `datetime-local` input value for an ISO instant, in the UI time zone. */
export function isoToLocalInput(iso: string): string {
  if (!iso || Number.isNaN(Date.parse(iso))) return "";
  return toDateTimeLocal(iso);
}

/** ISO instant with an explicit UTC offset for a `datetime-local` value, or "" when incomplete. */
export function localInputToIso(value: string): string {
  const date = dateTimeLocalToDate(value);
  return date ? date.toISOString() : "";
}

/** An absolute period covering the same span as `days` ending now. */
export function absoluteFromDays(days: number, now: Date = new Date()): MetricPeriod {
  const start = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
  return { kind: "absolute", start: start.toISOString(), end: now.toISOString() };
}
