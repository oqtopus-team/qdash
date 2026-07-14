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
