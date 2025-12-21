import { formatInTimeZone } from "date-fns-tz";

const DEFAULT_TIMEZONE = "Asia/Tokyo";

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
    return formatInTimeZone(utcString, timezone, format);
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
