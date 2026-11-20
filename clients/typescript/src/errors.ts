export interface QDashErrorOptions {
  statusCode?: number;
  payload?: unknown;
  cause?: unknown;
}

export class QDashApiError extends Error {
  readonly statusCode?: number;
  readonly payload?: unknown;

  constructor(message: string, options: QDashErrorOptions = {}) {
    super(message, { cause: options.cause });
    this.name = new.target.name;
    this.statusCode = options.statusCode;
    this.payload = options.payload;
  }
}

export class QDashConfigError extends Error {
  constructor(message: string, options: { cause?: unknown } = {}) {
    super(message, options);
    this.name = "QDashConfigError";
  }
}

export class QDashAuthError extends QDashApiError {}
export class QDashNotFoundError extends QDashApiError {}
export class QDashValidationError extends QDashApiError {}
export class QDashTransportError extends QDashApiError {}

export const QDashClientError = QDashApiError;

/**
 * A polling helper gave up waiting. Waiting is client-side only: the execution or
 * operation it waited for is not cancelled and keeps running in QDash.
 */
export class QDashTimeoutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "QDashTimeoutError";
  }
}
