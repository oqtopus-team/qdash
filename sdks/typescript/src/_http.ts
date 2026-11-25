/** Building the generated client from a config, the SDK's error translation and read retries. */
import { randomUUID } from "node:crypto";
import { createRequire } from "node:module";
import { setTimeout as delay } from "node:timers/promises";

import { ApiError, ApiTimeoutError, QDashApiClient } from "./_generated/index.js";
import { isResponseBodyError } from "./_generated/core/fetcher/getResponseBody.js";
import type { RawResponse } from "./_generated/core/index.js";
import type { QDashConfig } from "./config.js";
import {
  QDashApiError,
  QDashAuthError,
  QDashConfigError,
  QDashConflictError,
  QDashNotFoundError,
  QDashResultUnknownError,
  QDashTransportError,
  QDashValidationError,
} from "./errors.js";

export type Fetch = typeof fetch;
export type Sleep = (milliseconds: number) => Promise<void>;
type Environment = Readonly<Record<string, string | undefined>>;

const STATUS_ERRORS: Record<number, typeof QDashApiError> = {
  401: QDashAuthError,
  403: QDashAuthError,
  404: QDashNotFoundError,
  409: QDashConflictError,
  422: QDashValidationError,
};
// Statuses after which a read is sent again; writes are never sent again.
const RETRYABLE_STATUSES = new Set([408, 429, 500, 502, 503, 504]);
const RETRY_BASE_SECONDS = 0.2;
const RETRY_MAX_SECONDS = 5;

function sdkVersion(): string {
  try {
    // dist/index.js and src/_http.ts both sit one level below package.json.
    const manifest = createRequire(import.meta.url)("../package.json") as { name?: string; version?: string };
    return manifest.name === "@oqtopus-team/qdash-sdk" && manifest.version ? manifest.version : "unknown";
  } catch {
    return "unknown";
  }
}

const SDK_VERSION = sdkVersion();

export function userAgent(config: QDashConfig): string {
  return config.userAgent ?? `qdash-sdk-ts/${SDK_VERSION}`;
}

/** Headers every request carries, besides the token and `X-Project-Id`. */
export function commonHeaders(config: QDashConfig): Record<string, string> {
  return {
    Accept: "application/json",
    "User-Agent": userAgent(config),
    ...(config.cfAccessClientId ? { "CF-Access-Client-Id": config.cfAccessClientId } : {}),
    ...(config.cfAccessClientSecret ? { "CF-Access-Client-Secret": config.cfAccessClientSecret } : {}),
  };
}

/** The fetch a session uses; proxy and TLS overrides cannot be applied by the built-in one. */
export function sessionFetch(config: QDashConfig, custom: Fetch | undefined): Fetch | undefined {
  if (custom === undefined && (config.proxy || !config.verifyTls)) {
    throw new QDashConfigError(
      "proxy and verifyTls=false need a custom fetch (the session's fetch option) that applies them; " +
        "the built-in fetch cannot, and the SDK does not ignore them.",
    );
  }
  return custom;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** How a session authenticates its API requests. */
export interface SessionAuth {
  /** The bearer token, or a function returning the current sign-in's token. */
  readonly token: string | (() => Promise<string>);
  /**
   * The fetch API requests go through: the given one, or, for a username/password sign-in, a
   * wrapper that drops the sign-in after a 401. Undefined means the built-in fetch.
   */
  readonly fetch: Fetch | undefined;
}

function bearerValue(input: RequestInfo | URL, init: RequestInit | undefined): { headers: Headers; value: string | undefined } {
  const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
  const match = /^Bearer\s+(.+)$/i.exec(headers.get("Authorization") ?? "");
  return { headers, value: match?.[1] };
}

/**
 * The session's authentication: a configured API token as it is, or a username/password
 * sign-in shared by every request of the session and of its `withProject` sessions.
 *
 * A sign-in happens once, on the first request, and is reused. A 401 answer to a request
 * drops the sign-in that request was sent with, so the next request signs in again; a 401 to a
 * request of an older sign-in leaves a newer one in place, even when the server issued the same
 * token string again. The request that got the 401 is not sent again (a write could act twice):
 * its caller gets the 401.
 *
 * Each request is tied to its sign-in by identity, not by token text: the generated client gets
 * a per-session marker carrying the sign-in's number and token, and the session's fetch replaces
 * it with the token right before sending, so the marker never reaches the network or the
 * caller's fetch. The request owns that state; the session keeps only the current sign-in, so
 * nothing accumulates across sign-ins or requests that never reach fetch.
 */
export function sessionAuth(config: QDashConfig, fetchFn: Fetch | undefined, env: Environment): SessionAuth {
  if (config.apiToken) return { token: config.apiToken, fetch: fetchFn };
  if (!config.username) {
    throw new QDashConfigError(
      "No authentication configured: set QDASH_API_TOKEN (api_token or api_token_env), or username " +
        "with the password in the environment variable password_env.",
    );
  }
  const { username, passwordEnv } = config;
  if (!passwordEnv) throw new QDashConfigError("password_env is required when using username/password");
  const signIn = async (): Promise<string> => {
    const password = env[passwordEnv];
    if (!password) throw new QDashConfigError(`Missing password in environment variable ${passwordEnv}`);
    // The login route takes no token; the generated client sends it without auth.
    const login = new QDashApiClient({
      environment: config.baseUrl,
      // auth: false sends no Authorization header; the token option is then unused.
      auth: false,
      token: "",
      headers: commonHeaders(config),
      timeoutInSeconds: config.timeoutSec,
      maxRetries: 0,
      ...(fetchFn ? { fetch: fetchFn } : {}),
    });
    let payload: unknown;
    try {
      payload = await login.auth.login({ username, password });
    } catch (error) {
      if (error instanceof ApiError && error.statusCode !== undefined && error.statusCode < 400) {
        throw new QDashAuthError("Login response was not valid JSON", { statusCode: error.statusCode });
      }
      throw translate(error);
    }
    if (isResponseBodyError(payload)) throw new QDashAuthError("Login response was not valid JSON");
    if (!isRecord(payload)) throw new QDashAuthError("Login response must be a JSON object");
    const token = payload.access_token;
    if (typeof token !== "string" || !token) throw new QDashAuthError("Login response did not include access_token");
    return token;
  };

  // Marker prefix of this session's sign-ins; random so it cannot match a real token.
  const marker = `qdash-sdk-sign-in-${randomUUID()}-`;
  // The current sign-in, shared by concurrent requests, and its number once it has a token.
  // Only numbers are kept: a request carries its own sign-in's token in its marker.
  let issued = 0;
  let pending: Promise<{ number: number; token: string }> | undefined;
  let current: number | undefined;
  const signedIn = (): Promise<{ number: number; token: string }> => {
    if (pending) return pending;
    const attempt: Promise<{ number: number; token: string }> = signIn().then(
      (value) => {
        issued += 1;
        if (pending === attempt) current = issued;
        return { number: issued, token: value };
      },
      (error: unknown) => {
        // A failed sign-in is tried again by the next request.
        if (pending === attempt) pending = undefined;
        throw error;
      },
    );
    pending = attempt;
    return attempt;
  };
  const token = async (): Promise<string> => {
    const { number, token: value } = await signedIn();
    return `${marker}${number}:${value}`;
  };
  const base: Fetch = fetchFn ?? ((input, init) => globalThis.fetch(input, init));
  const apiFetch = (async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const { headers, value } = bearerValue(input, init);
    // A request without the session's marker (no auth, or the caller's own Authorization).
    if (value === undefined || !value.startsWith(marker)) return base(input, init);
    const carried = /^(\d+):(.+)$/s.exec(value.slice(marker.length));
    if (!carried) throw new QDashAuthError("Malformed sign-in marker for this request; nothing was sent");
    const signInNumber = Number(carried[1]);
    headers.set("Authorization", `Bearer ${carried[2]}`);
    const response = await base(input, { ...init, headers });
    // Only the sign-in this request was sent with is dropped; a newer one stays.
    if (response.status === 401 && signInNumber === current) {
      pending = undefined;
      current = undefined;
    }
    return response;
  }) as Fetch;
  return { token, fetch: apiFetch };
}

export interface ApiOptions {
  projectId: string | undefined;
  fetch: Fetch | undefined;
  token: string | (() => Promise<string>);
}

/**
 * The generated client for `config`, scoped to `projectId`. Retries are off unless a call asks
 * for them, so a request that changes state is sent once even after a 409, a 5xx or a timeout.
 */
export function buildApi(config: QDashConfig, options: ApiOptions): QDashApiClient {
  return new QDashApiClient({
    environment: config.baseUrl,
    token: options.token,
    ...(options.projectId !== undefined ? { projectId: options.projectId } : {}),
    headers: commonHeaders(config),
    timeoutInSeconds: config.timeoutSec,
    maxRetries: 0,
    ...(options.fetch ? { fetch: options.fetch } : {}),
  });
}

/**
 * Render an error `detail` as readable text. FastAPI validation errors carry a list of
 * `{ loc, msg }` objects, which `String()` would turn into "[object Object]".
 */
function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(formatDetail).join("; ");
  if (isRecord(detail)) {
    const { loc, msg } = detail;
    if (typeof msg === "string") {
      // loc starts with where the value came from ("body", "query", ...).
      const path = Array.isArray(loc) ? loc.slice(1).join(".") : "";
      return path ? `${path}: ${msg}` : msg;
    }
    return JSON.stringify(detail);
  }
  return String(detail);
}

function endpoint(error: ApiError): string {
  const url = error.rawResponse?.url;
  if (!url) return "";
  try {
    return ` ${new URL(url).pathname}`;
  } catch {
    return "";
  }
}

/** The SDK error for an error of the generated client; other errors are returned unchanged. */
export function translate(error: unknown): unknown {
  if (error instanceof QDashApiError || !(error instanceof ApiError)) return error;
  if (error instanceof ApiTimeoutError) {
    return new QDashTransportError(`QDash request timed out: ${error.message}`, { cause: error });
  }
  const status = error.statusCode;
  const common = {
    ...(status !== undefined ? { statusCode: status } : {}),
    ...(error.body !== undefined ? { body: error.body } : {}),
    ...(error.rawResponse !== undefined ? { rawResponse: error.rawResponse } : {}),
    cause: error,
  };
  if (status === undefined) {
    const reason = error.message.split("\n")[0] || "no response";
    return new QDashTransportError(`QDash request failed: ${reason}`, common);
  }
  if (status < 400) {
    return new QDashTransportError(`${status}${endpoint(error)}: the response is not valid JSON`, common);
  }
  const body = error.body;
  const detail = isRecord(body) && "detail" in body ? body.detail : typeof body === "string" ? body : undefined;
  const message = `${status}${endpoint(error)}${detail ? `: ${formatDetail(detail)}` : ""}`;
  const ErrorClass = STATUS_ERRORS[status] ?? QDashApiError;
  return new ErrorClass(message, common);
}

/** Await a generated call, raising the SDK's errors; a caller's abort rejects with its reason. */
export async function call<T>(request: () => Promise<T>, signal?: AbortSignal): Promise<T> {
  try {
    return await request();
  } catch (error) {
    if (signal?.aborted) throw signal.reason ?? error;
    throw translate(error);
  }
}

/** Request options of a generated call the SDK sends: never retried by the generated client. */
export interface CallOptions {
  maxRetries: 0;
  abortSignal?: AbortSignal;
}

export interface ReadPolicy {
  /** Attempts in total, at least 1 (`QDashConfig.readAttempts`). */
  attempts: number;
  sleep: Sleep;
  signal?: AbortSignal;
}

function retryable(error: unknown): boolean {
  if (!(error instanceof QDashApiError)) return false;
  if (error.statusCode === undefined) return error instanceof QDashTransportError;
  return RETRYABLE_STATUSES.has(error.statusCode);
}

function retryDelayMilliseconds(attempt: number, error: QDashApiError): number {
  const retryAfter = error.rawResponse?.headers.get("Retry-After");
  if (retryAfter) {
    const seconds = Number(retryAfter);
    if (Number.isFinite(seconds) && seconds >= 0) return Math.min(seconds, RETRY_MAX_SECONDS) * 1_000;
  }
  return Math.min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * 2 ** (attempt - 1)) * 1_000;
}

/**
 * A GET the SDK may send again: after a transport error (no response, timeout) or a status of
 * 408, 429, 500, 502, 503 or 504, up to `policy.attempts` in total. This is the only retry
 * layer: the generated client is told not to retry. A caller's abort is never retried.
 */
export async function read<T>(policy: ReadPolicy, request: (options: CallOptions) => Promise<T>): Promise<T> {
  const options: CallOptions = { maxRetries: 0, ...(policy.signal ? { abortSignal: policy.signal } : {}) };
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await call(() => request(options), policy.signal);
    } catch (error) {
      if (attempt >= policy.attempts || policy.signal?.aborted || !retryable(error)) throw error;
      await policy.sleep(retryDelayMilliseconds(attempt, error as QDashApiError));
    }
  }
}

/**
 * The error for a dispatch answer that does not confirm how the run was recorded: the run may
 * have started, so it is reported for reconciliation, never sent again.
 */
export function resultUnknown(message: string, answer: { data: unknown; rawResponse: RawResponse }): QDashResultUnknownError {
  const data = answer.data;
  const executionId = isRecord(data) && typeof data.execution_id === "string" && data.execution_id ? data.execution_id : undefined;
  return new QDashResultUnknownError(message, {
    statusCode: answer.rawResponse.status,
    body: data,
    rawResponse: answer.rawResponse,
    ...(executionId ? { executionId } : {}),
  });
}

const UNDECODABLE_DISPATCH =
  "the dispatch was accepted but its answer could not be read, so the run may have started. " +
  "Do not retry automatically or use a new key; reconcile the execution first.";

/**
 * Send a dispatch once and return its answer. A success status whose body is not a JSON
 * object (truncated, not JSON or empty) throws `QDashResultUnknownError`, with the status, body
 * and raw response of the answer and the client's error as cause: the server accepted the
 * request, so the run may have started. Error statuses and transport errors are thrown as by
 * `call`; nothing is sent again.
 */
export async function dispatch<T>(
  what: string,
  request: () => Promise<{ data: T; rawResponse: RawResponse }>,
): Promise<{ data: T; rawResponse: RawResponse }> {
  let answer: { data: T; rawResponse: RawResponse };
  try {
    answer = await request();
  } catch (error) {
    if (
      error instanceof ApiError &&
      !(error instanceof ApiTimeoutError) &&
      error.statusCode !== undefined &&
      error.statusCode >= 200 &&
      error.statusCode < 400
    ) {
      throw new QDashResultUnknownError(`${what} result unknown: ${UNDECODABLE_DISPATCH}`, {
        statusCode: error.statusCode,
        ...(error.body !== undefined ? { body: error.body } : {}),
        ...(error.rawResponse !== undefined ? { rawResponse: error.rawResponse } : {}),
        cause: error,
      });
    }
    throw translate(error);
  }
  const data: unknown = answer.data;
  if (isResponseBodyError(data) || !isRecord(data)) {
    const body = isResponseBodyError(data) && data.error.reason === "non-json" ? data.error.rawBody : data;
    throw new QDashResultUnknownError(`${what} result unknown: ${UNDECODABLE_DISPATCH}`, {
      statusCode: answer.rawResponse.status,
      ...(body !== undefined ? { body } : {}),
      rawResponse: answer.rawResponse,
    });
  }
  return answer;
}

/** Options of a write: sent once. */
export function writeOptions(signal?: AbortSignal): CallOptions {
  return { maxRetries: 0, ...(signal ? { abortSignal: signal } : {}) };
}

export const defaultSleep: Sleep = (milliseconds) => delay(milliseconds);

/** What the helpers of one session share: the generated client, its config and read policy. */
export interface Context {
  readonly api: QDashApiClient;
  readonly config: QDashConfig;
  readonly reads: ReadPolicy;
  readonly sleep: Sleep;
  /** Milliseconds of a monotonic-enough clock, for polling deadlines. */
  readonly now: () => number;
}
