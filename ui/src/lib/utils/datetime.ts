import { formatInTimeZone } from "date-fns-tz";

const DEFAULT_TIMEZONE = process.env.NEXT_PUBLIC_TIMEZONE || "Asia/Tokyo";
const ISO_DATETIME_WITHOUT_TIMEZONE =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/;

function normalizeUtcInput(utcString: string): string {
  if (ISO_DATETIME_WITHOUT_TIMEZONE.test(utcString)) {
    return `${utcString}Z`;
  }
  return utcString;
}

function parseUtcDate(utcString: string): Date {
  return new Date(normalizeUtcInput(utcString));
}

export function dateToDateTimeLocal(
  date: Date,
  timezone: string = DEFAULT_TIMEZONE,
): string {
  return formatInTimeZone(date, timezone, "yyyy-MM-dd'T'HH:mm");
}

export function dateToDateInput(
  date: Date,
  timezone: string = DEFAULT_TIMEZONE,
): string {
  return formatInTimeZone(date, timezone, "yyyy-MM-dd");
}

export function toDateTimeLocal(
  isoString: string | null | undefined,
  timezone: string = DEFAULT_TIMEZONE,
): string {
  if (!isoString) return "";
  if (isoString.includes("T")) {
    return formatInTimeZone(
      normalizeUtcInput(isoString),
      timezone,
      "yyyy-MM-dd'T'HH:mm",
    );
  }
  return `${isoString}T00:00`;
}

export function toIsoSeconds(
  dt: string,
  timezone: string = DEFAULT_TIMEZONE,
): string {
  if (dt.length === 16)
    return `${dt}:00${getTimezoneOffsetString(timezone, dt)}`;
  return dt;
}

export function getTimezoneOffsetString(
  timezone: string = DEFAULT_TIMEZONE,
  referenceDate: Date | string = new Date(),
): string {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    timeZoneName: "longOffset",
  });
  const part = fmt
    .formatToParts(new Date(referenceDate))
    .find((p) => p.type === "timeZoneName");
  const raw = part?.value ?? "GMT";
  if (raw === "GMT") return "+00:00";
  return raw.replace("GMT", "");
}

/**
 * Format a UTC datetime string to local timezone.
 *
 * @param utcString - ISO8601 datetime string (e.g., "2025-12-21T00:44:31+00:00")
 * @param format - Output format (default: "yyyy-MM-dd HH:mm:ss")
 * @param timezone - Target timezone (default: "Asia/Tokyo")
 * @returns Formatted datetime string or "-" if input is null/undefined
 */
export function formatDateTime(
  utcString: string | null | undefined,
  format: string = "yyyy-MM-dd HH:mm:ss",
  timezone: string = DEFAULT_TIMEZONE,
): string {
  if (!utcString) return "-";
  try {
    return formatInTimeZone(normalizeUtcInput(utcString), timezone, format);
  } catch {
    return utcString;
  }
}

/**
 * Format a UTC datetime string to date only.
 *
 * @param utcString - ISO8601 datetime string
 * @param timezone - Target timezone (default: "Asia/Tokyo")
 * @returns Formatted date string (yyyy-MM-dd) or "-" if input is null/undefined
 */
export function formatDate(
  utcString: string | null | undefined,
  timezone: string = DEFAULT_TIMEZONE,
): string {
  return formatDateTime(utcString, "yyyy-MM-dd", timezone);
}

/**
 * Format a UTC datetime string to time only.
 *
 * @param utcString - ISO8601 datetime string
 * @param timezone - Target timezone (default: "Asia/Tokyo")
 * @returns Formatted time string (HH:mm:ss) or "-" if input is null/undefined
 */
export function formatTime(
  utcString: string | null | undefined,
  timezone: string = DEFAULT_TIMEZONE,
): string {
  return formatDateTime(utcString, "HH:mm:ss", timezone);
}

/**
 * Format a UTC datetime string to a compact format.
 *
 * @param utcString - ISO8601 datetime string
 * @param timezone - Target timezone (default: "Asia/Tokyo")
 * @returns Formatted datetime string (MM/dd HH:mm) or "-" if input is null/undefined
 */
export function formatDateTimeCompact(
  utcString: string | null | undefined,
  timezone: string = DEFAULT_TIMEZONE,
): string {
  return formatDateTime(utcString, "MM/dd HH:mm", timezone);
}

/**
 * Format a UTC datetime string to relative time (e.g., "5m ago", "2h ago").
 *
 * @param utcString - ISO8601 datetime string
 * @param timezone - Target timezone (default: from env or "Asia/Tokyo")
 * @returns Relative time string or "" if input is null/undefined
 */
export function formatRelativeTime(
  utcString: string | null | undefined,
  timezone: string = DEFAULT_TIMEZONE,
): string {
  if (!utcString) return "";

  try {
    const diffMs = Date.now() - parseUtcDate(utcString).getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    // For older dates, show the formatted date
    return formatDateTime(utcString, "MM/dd", timezone);
  } catch {
    return "";
  }
}
