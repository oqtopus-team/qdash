/**
 * Timestamps QDash's API returns.
 *
 * QDash stores and returns datetimes in UTC. Its responses may omit the offset
 * (`2026-11-22T02:53:20.768000`), and such a value still names a UTC instant:
 * the backend's `ensure_timezone` treats a naive datetime as UTC, and the UI's
 * `normalizeUtcInput` reads it the same way. JavaScript's `Date` reads a
 * date-time without an offset as host-local time, which shifts the instant by
 * the host's offset (nine hours under Asia/Tokyo). Read API timestamps here
 * instead of `new Date(...)` or `Date.parse(...)`.
 *
 * Only ISO 8601 date-times are accepted. Anything else, such as a date without
 * a time or a free-form date, yields `NaN` rather than a guessed instant, so a
 * caller can fail closed.
 */

const SERVER_DATETIME = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)(Z|[+-]\d{2}:?\d{2})?$/i;

/** The value with an explicit offset: `Z` appended to a naive value, a `+hhmm` offset given its colon. */
function zoned(value: string): string | undefined {
  const match = SERVER_DATETIME.exec(value.trim());
  if (!match) return undefined;
  const [, local, zone] = match;
  if (!zone) return `${local}Z`;
  if (zone.toUpperCase() === "Z") return `${local}Z`;
  return zone.includes(":") ? `${local}${zone}` : `${local}${zone.slice(0, 3)}:${zone.slice(3)}`;
}

/**
 * Epoch milliseconds of an API timestamp, or `NaN` when the value is not a
 * valid ISO date-time. A naive value is UTC; an explicit `Z` or offset is kept.
 */
export function parseServerTimestamp(value: unknown): number {
  if (value instanceof Date) return value.getTime();
  if (typeof value !== "string") return Number.NaN;
  const text = zoned(value);
  return text === undefined ? Number.NaN : Date.parse(text);
}

/**
 * The timestamp as text that names its instant unambiguously: a naive API
 * value gains `Z`, a value with an offset is returned unchanged, and a `Date`
 * becomes its ISO string. Text that is not an ISO date-time is returned as is,
 * so a reader still sees what QDash sent.
 */
export function serverTimestampText(value: unknown): string {
  if (value instanceof Date) return value.toISOString();
  const text = typeof value === "string" ? value : String(value ?? "");
  const match = SERVER_DATETIME.exec(text.trim());
  return match && !match[2] ? `${match[1]}Z` : text;
}

/** Order two API timestamps oldest first; invalid values sort last and keep their relative order. */
export function compareServerTimestamps(a: unknown, b: unknown): number {
  const left = parseServerTimestamp(a);
  const right = parseServerTimestamp(b);
  const leftValid = Number.isFinite(left);
  const rightValid = Number.isFinite(right);
  if (leftValid && rightValid) return left - right;
  if (leftValid) return -1;
  if (rightValid) return 1;
  return 0;
}
