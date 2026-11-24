/**
 * Errors raised by the QDash SDK.
 *
 * `QDashApiError` extends the generated client's `ApiError`, so `instanceof ApiError` catches
 * both the errors of the SDK operations and those of the generated resource clients reached
 * through `QDash.api`. The SDK operations raise the subclass matching the HTTP status; the
 * generated resource clients raise `ApiError` (`QDashApi.UnprocessableEntityError` for 422
 * and so on) and `ApiTimeoutError`.
 */
import { ApiError, ApiTimeoutError } from "./_generated/index.js";
import type { RawResponse } from "./_generated/core/index.js";

export { ApiError, ApiTimeoutError };

/** The SDK configuration is missing or invalid; nothing was sent. Messages never carry secrets. */
export class QDashConfigError extends Error {
  constructor(message: string, options: { cause?: unknown } = {}) {
    super(message, options);
    this.name = "QDashConfigError";
  }
}

export interface QDashErrorOptions {
  /** The HTTP status, or undefined when no response arrived. */
  statusCode?: number;
  /** The response body as the server sent it, decoded from JSON when possible. */
  body?: unknown;
  rawResponse?: RawResponse;
  cause?: unknown;
}

/**
 * A QDash API request failed. `statusCode` is the HTTP status, or undefined when no response
 * arrived; `body` (also `payload`) is the response body, decoded from JSON when possible.
 */
export class QDashApiError extends ApiError {
  constructor(message: string, options: QDashErrorOptions = {}) {
    super({
      message,
      ...(options.statusCode !== undefined ? { statusCode: options.statusCode } : {}),
      ...(options.body !== undefined ? { body: options.body } : {}),
      ...(options.rawResponse !== undefined ? { rawResponse: options.rawResponse } : {}),
      ...(options.cause !== undefined ? { cause: options.cause } : {}),
    });
    // ApiError appends the status and body to the message; the SDK states them itself.
    this.message = message;
    this.name = new.target.name;
  }

  /** The response body; the same as `body`. */
  get payload(): unknown {
    return this.body;
  }
}

/** The request was not authenticated or not allowed (401 or 403). */
export class QDashAuthError extends QDashApiError {}

/** The requested resource does not exist (404). */
export class QDashNotFoundError extends QDashApiError {}

/**
 * The request conflicts with the stored state (409), such as a stale revision. Nothing is
 * retried: read the current state and decide whether to save again.
 */
export class QDashConflictError extends QDashApiError {}

/** The server rejected the request's parameters or body (422), or the SDK did before sending. */
export class QDashValidationError extends QDashApiError {}

/**
 * No usable response: the connection failed or timed out, or the response did not parse. For a
 * request that changes state, the server may still have acted on it.
 */
export class QDashTransportError extends QDashApiError {}

/**
 * A dispatch was answered, but the answer does not show the run was recorded as requested
 * (its calibration session, retry key or decision), for example from a server that predates
 * run recording and ignores them. The run may have started anyway. Do not send it again or
 * with a new key: reconcile it first, from `executionId` when the answer carries one.
 * `statusCode`, `body` and `rawResponse` are those of the dispatch answer.
 */
export class QDashResultUnknownError extends QDashApiError {
  /** The execution the answer names, if any: where to start reconciling. */
  readonly executionId: string | undefined;

  constructor(message: string, options: QDashErrorOptions & { executionId?: string } = {}) {
    super(message, options);
    this.executionId = options.executionId;
  }
}

/**
 * A polling helper gave up waiting. Waiting is client-side only: the run it waited for is not
 * cancelled and keeps running in QDash.
 */
export class QDashTimeoutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "QDashTimeoutError";
  }
}
