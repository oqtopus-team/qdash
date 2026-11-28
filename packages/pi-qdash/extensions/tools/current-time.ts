import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

import { DEFAULT_HOST_NAME, HOST_NAME_KEY } from "../lib/host-model.js";
import { toTextToolResult } from "../lib/results.js";

/**
 * The current time, read when the tool runs.
 *
 * A model has no clock: it guesses the date from its training data or from
 * dates in the conversation, and a timestamp put into the system prompt goes
 * stale as a conversation runs on. `qdash_current_time` reads the clock of the
 * process running the tool, at every call, so a new turn or a repeated call
 * gets a fresh reading.
 *
 * The source is the operating system clock of the process running the tool:
 * the machine running pi CLI, or the QDash Agent Runtime's container. It is
 * not the QDash API server's clock and not a measurement time, and this tool
 * does not check it against any time service; a result's own timestamps say
 * when it was measured, and QDash timestamps without an offset are UTC (see
 * lib/server-time.ts).
 *
 * The user's time zone is never inferred: not from their language, and not
 * from the process's `TZ` or the container's zone, which are deployment
 * settings. The answer is UTC unless the call names an IANA time zone the user
 * stated; an unknown name is refused rather than guessed. The UTC instant and
 * an explicitly named zone's rendering do not depend on the process's zone.
 */

export type CurrentTimeDependencies = {
  /** The clock; tests freeze it. */
  now?: () => Date;
};

/** One instant as seen in one time zone. */
export type ZonedTime = {
  time_zone: string;
  /** ISO 8601 local time with its offset, millisecond precision. */
  local: string;
  /** Offset from UTC as `+09:00`, `-05:00`, or `+00:00`. */
  offset: string;
  weekday: string;
};

export type CurrentTimeReading = {
  utc: string;
  epoch_ms: number;
  weekday_utc: string;
  /** The OS clock of the process that ran the tool; not synchronized or verified by this tool. */
  source: { kind: "host_os_clock"; host: string; verified: false };
  /** The zone the call named, which the user stated; null when none was named. */
  requested: ZonedTime | null;
  user_time_zone_known: boolean;
};

const IANA_NAME = /^[A-Za-z][A-Za-z0-9_+-]*(?:\/[A-Za-z0-9_+-]+)*$/;

/** The canonical name of an IANA time zone, or undefined when the runtime does not know it. */
export function canonicalTimeZone(name: string): string | undefined {
  const trimmed = name.trim();
  // Offsets such as "+09:00" are not zones: they carry no daylight saving rules.
  if (!IANA_NAME.test(trimmed)) return undefined;
  try {
    return new Intl.DateTimeFormat("en-US", { timeZone: trimmed }).resolvedOptions().timeZone;
  } catch {
    return undefined;
  }
}

function pad(value: number, width = 2): string {
  return String(Math.abs(value)).padStart(width, "0");
}

function formatOffset(minutes: number): string {
  const sign = minutes < 0 ? "-" : "+";
  return `${sign}${pad(Math.trunc(Math.abs(minutes) / 60))}:${pad(Math.abs(minutes) % 60)}`;
}

/** `instant` in `timeZone`, which must be a zone the runtime knows. */
export function zonedTime(instant: Date, timeZone: string): ZonedTime {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      weekday: "long",
    })
      .formatToParts(instant)
      .map((part) => [part.type, part.value]),
  );
  const [year, month, day, hour, minute, second] = ["year", "month", "day", "hour", "minute", "second"].map((key) => Number(parts[key]));
  const millisecond = instant.getUTCMilliseconds();
  const wall = Date.UTC(year, month - 1, day, hour, minute, second, millisecond);
  const offsetMinutes = Math.round((wall - instant.getTime()) / 60_000);
  const offset = formatOffset(offsetMinutes);
  const local = `${pad(year, 4)}-${pad(month)}-${pad(day)}T${pad(hour)}:${pad(minute)}:${pad(second)}.${pad(millisecond, 3)}${offset}`;
  return { time_zone: timeZone, local, offset, weekday: String(parts.weekday) };
}

/** Read `now` as UTC, and in `requestedZone` when given; throws for an unknown zone. */
export function readCurrentTime(now: Date, options: { requestedZone?: string; host?: string } = {}): CurrentTimeReading {
  let requested: ZonedTime | null = null;
  if (options.requestedZone !== undefined) {
    const zone = canonicalTimeZone(options.requestedZone);
    if (!zone) {
      throw new Error(
        `Unknown time zone ${JSON.stringify(options.requestedZone)}: pass an IANA time zone name such as "Asia/Tokyo", "America/New_York", or "UTC". No time was converted.`,
      );
    }
    requested = zonedTime(now, zone);
  }
  return {
    utc: now.toISOString(),
    epoch_ms: now.getTime(),
    weekday_utc: zonedTime(now, "UTC").weekday,
    source: { kind: "host_os_clock", host: options.host ?? DEFAULT_HOST_NAME, verified: false },
    requested,
    user_time_zone_known: requested !== null,
  };
}

const HOST_LABELS: Record<string, string> = {
  pi: "the machine running pi CLI",
  "qdash-web-agent": "the QDash web agent runtime's container",
};

export function formatCurrentTime(reading: CurrentTimeReading): string {
  const host = HOST_LABELS[reading.source.host] ?? `the ${reading.source.host} host`;
  const lines = [`Current time, read from the operating system clock of ${host} when this tool ran:`, `- UTC: ${reading.utc} (${reading.weekday_utc})`];
  if (reading.requested) {
    const zone = reading.requested;
    lines.push(`- ${zone.time_zone}: ${zone.local} (${zone.weekday}, UTC${zone.offset})`);
  } else {
    lines.push(
      "The user's time zone is not known, so this answer is in UTC. Do not infer it from the user's language or from the host's or container's time zone setting; when the user names a time zone, call this tool again with timeZone.",
    );
  }
  lines.push(
    "This clock is the host's, not the QDash server's or the measurement hardware's, and this tool does not verify it against a time service. When a result was measured comes from its own timestamps; QDash timestamps without an offset are UTC.",
    "Call this tool again whenever you need the time later; do not reuse this reading.",
  );
  return lines.join("\n");
}

function hostName(ctx: unknown): string {
  const named = ctx && typeof ctx === "object" ? (ctx as Record<string, unknown>)[HOST_NAME_KEY] : undefined;
  return typeof named === "string" && /^[a-z0-9][a-z0-9._-]{0,63}$/.test(named) ? named : DEFAULT_HOST_NAME;
}

export function registerCurrentTimeTool(pi: Pick<ExtensionAPI, "registerTool">, deps: CurrentTimeDependencies = {}): void {
  const now = deps.now ?? (() => new Date());
  pi.registerTool({
    name: "qdash_current_time",
    label: "Current Time",
    description:
      "Read the current date and time from the host's operating system clock when the tool runs: UTC, and the local time and offset in an IANA time zone when one is given. Read-only; needs no QDash connection and no approval. Use it whenever the answer depends on today's date or the current time.",
    promptSnippet: "Read the current date and time (UTC, or an IANA time zone the user named)",
    promptGuidelines: [
      "Call qdash_current_time whenever an answer depends on the current date or time, such as \"today\", \"the last 24 hours\", or how long ago something ran; do not take the date from memory or from earlier messages, and call it again in a later turn instead of reusing an old reading.",
      "Pass timeZone to qdash_current_time only when the user named a time zone; never infer it from the user's language, name, or the host's time zone. Without one, give times in UTC and say so.",
    ],
    parameters: Type.Object({
      timeZone: Type.Optional(Type.String({ description: "IANA time zone the user named, such as \"Asia/Tokyo\" or \"America/New_York\". Omit when the user named none; the answer is then UTC." })),
    }),
    async execute(_toolCallId, params: { timeZone?: string }, _signal, _onUpdate, ctx) {
      const reading = readCurrentTime(now(), { requestedZone: params.timeZone, host: hostName(ctx) });
      return toTextToolResult(formatCurrentTime(reading), reading, { tool: "qdash_current_time" });
    },
  });
}
