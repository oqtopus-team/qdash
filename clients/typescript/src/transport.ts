import { setTimeout as sleep } from "node:timers/promises";

import type { AxiosRequestConfig } from "axios";

import { QDashConfig } from "./config.js";
import {
  QDashApiError,
  QDashAuthError,
  QDashNotFoundError,
  QDashTransportError,
  QDashValidationError,
} from "./errors.js";

export type Fetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export type QueryValue = string | number | boolean | null | undefined | readonly string[];

export interface RequestOptions {
  query?: Record<string, QueryValue>;
  body?: unknown;
  headers?: HeadersInit;
}

export interface TransportOptions {
  fetch?: Fetch;
  defaultHeaders?: HeadersInit;
  sleep?: (milliseconds: number) => Promise<void>;
  random?: () => number;
  env?: Record<string, string | undefined>;
}

const RETRYABLE_STATUSES = new Set([408, 429, 500, 502, 503, 504]);

async function responsePayload(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function errorMessage(response: Response, payload: unknown): string {
  let detail: unknown;
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    detail = (payload as { detail?: unknown }).detail;
  } else if (typeof payload === "string") {
    detail = payload;
  }
  const endpoint = response.url ? new URL(response.url).pathname : "<unknown>";
  return `${response.status} ${endpoint}${detail ? `: ${String(detail)}` : ""}`;
}

export class QDashTransport {
  readonly fetch: Fetch;

  private token?: string;
  private readonly baseFetch: Fetch;
  private readonly defaultHeaders: Headers;
  private readonly sleep: (milliseconds: number) => Promise<void>;
  private readonly random: () => number;
  private readonly env: Record<string, string | undefined>;

  constructor(
    readonly config: QDashConfig,
    options: TransportOptions = {},
  ) {
    if ((config.proxy || !config.verifyTls) && !options.fetch) {
      throw new QDashTransportError(
        "proxy and verifyTls overrides require a custom fetch implementation",
      );
    }
    this.baseFetch = options.fetch ?? globalThis.fetch.bind(globalThis);
    this.defaultHeaders = new Headers(options.defaultHeaders);
    this.sleep = options.sleep ?? ((milliseconds) => sleep(milliseconds));
    this.random = options.random ?? Math.random;
    this.env = options.env ?? process.env;
    this.token = config.apiToken;
    this.fetch = this.authorizedFetch.bind(this);
  }

  async requestJson<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
    return this.request<T>({
      method,
      url: path,
      params: options.query,
      data: options.body,
      ...(options.headers
        ? { headers: Object.fromEntries(new Headers(options.headers).entries()) }
        : {}),
    });
  }

  async request<T>(config: AxiosRequestConfig): Promise<T> {
    const requestUrl = config.url ?? "";
    const url = new URL(
      requestUrl.startsWith("http://") || requestUrl.startsWith("https://")
        ? requestUrl
        : this.config.baseUrl + (requestUrl.startsWith("/") ? "" : "/") + requestUrl,
    );
    for (const [key, value] of Object.entries(
      (config.params ?? {}) as Record<string, QueryValue>,
    )) {
      if (value === undefined || value === null) continue;
      if (Array.isArray(value)) {
        for (const item of value) url.searchParams.append(key, item);
      } else {
        url.searchParams.set(key, String(value));
      }
    }
    const headers = new Headers(config.headers as HeadersInit | undefined);
    let body: BodyInit | undefined;
    if (config.data !== undefined) {
      if (
        typeof config.data === "string" ||
        config.data instanceof URLSearchParams ||
        config.data instanceof FormData ||
        config.data instanceof Blob ||
        config.data instanceof ArrayBuffer
      ) {
        body = config.data as BodyInit;
      } else {
        if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
        body = JSON.stringify(config.data);
      }
    }
    const response = await this.fetch(url, {
      method: config.method ?? "GET",
      headers,
      ...(body === undefined ? {} : { body }),
    });
    let payload: unknown;
    if (config.responseType === "arraybuffer") payload = await response.arrayBuffer();
    else if (config.responseType === "blob") payload = await response.blob();
    else if (config.responseType === "text") payload = await response.text();
    else payload = await responsePayload(response);
    if (!response.ok) throw this.apiError(response, payload);
    return payload as T;
  }

  private async authorizedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const request = new Request(input, init);
    const headers = new Headers(this.defaultHeaders);
    request.headers.forEach((value, key) => headers.set(key, value));
    headers.set("Accept", "application/json");
    headers.set("User-Agent", this.config.userAgent);
    headers.set("Authorization", `Bearer ${await this.getToken()}`);
    this.setGatewayHeaders(headers);

    const authenticated = new Request(request, { headers });
    const retryableMethod = authenticated.method === "GET" || authenticated.method === "HEAD";
    const attempts = retryableMethod ? this.config.retry.maxAttempts : 1;

    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      try {
        const response = await this.fetchWithTimeout(authenticated.clone());
        if (response.status === 401 && !this.config.apiToken && this.config.username) {
          this.token = undefined;
        }
        if (!RETRYABLE_STATUSES.has(response.status) || attempt === attempts) return response;
        await this.sleep(this.retryDelayMilliseconds(attempt, response));
      } catch (cause) {
        if (cause instanceof QDashApiError) throw cause;
        if (attempt === attempts) {
          throw new QDashTransportError("QDash request failed", { cause });
        }
        await this.sleep(this.retryDelayMilliseconds(attempt));
      }
    }
    throw new QDashTransportError("QDash request exhausted all retries");
  }

  private async fetchWithTimeout(request: Request): Promise<Response> {
    const timeout = AbortSignal.timeout(this.config.timeoutSeconds * 1_000);
    const signal = request.signal.aborted
      ? request.signal
      : AbortSignal.any([request.signal, timeout]);
    return this.baseFetch(new Request(request, { signal }));
  }

  private async getToken(): Promise<string> {
    if (this.token) return this.token;
    if (!this.config.username) {
      throw new QDashAuthError("No authentication method configured", { statusCode: 401 });
    }
    const passwordEnv = this.config.passwordEnv;
    if (!passwordEnv) {
      throw new QDashAuthError("passwordEnv is required for username/password authentication", {
        statusCode: 401,
      });
    }
    const password = this.env[passwordEnv];
    if (!password) {
      throw new QDashAuthError(`Missing password in environment variable ${passwordEnv}`, {
        statusCode: 401,
      });
    }

    const headers = new Headers({
      Accept: "application/json",
      "Content-Type": "application/x-www-form-urlencoded",
      "User-Agent": this.config.userAgent,
    });
    this.setGatewayHeaders(headers);
    const response = await this.baseFetch(`${this.config.baseUrl}/auth/login`, {
      method: "POST",
      headers,
      body: new URLSearchParams({ username: this.config.username, password }),
      signal: AbortSignal.timeout(this.config.timeoutSeconds * 1_000),
    });
    const payload = await responsePayload(response);
    if (!response.ok) throw this.apiError(response, payload);
    const token =
      typeof payload === "object" && payload !== null && "access_token" in payload
        ? (payload as { access_token?: unknown }).access_token
        : undefined;
    if (typeof token !== "string" || !token) {
      throw new QDashAuthError("Login response did not include access_token", {
        statusCode: 401,
        payload,
      });
    }
    this.token = token;
    return token;
  }

  private setGatewayHeaders(headers: Headers): void {
    if (this.config.projectId) headers.set("X-Project-Id", this.config.projectId);
    if (this.config.cfAccessClientId) {
      headers.set("CF-Access-Client-Id", this.config.cfAccessClientId);
    }
    if (this.config.cfAccessClientSecret) {
      headers.set("CF-Access-Client-Secret", this.config.cfAccessClientSecret);
    }
  }

  private retryDelayMilliseconds(attempt: number, response?: Response): number {
    const retryAfter = response?.headers.get("Retry-After");
    if (retryAfter) {
      const seconds = Number(retryAfter);
      if (Number.isFinite(seconds)) return Math.max(0, seconds * 1_000);
    }
    const base = this.config.retry.baseDelaySeconds;
    const cap = this.config.retry.maxDelaySeconds;
    const delay = Math.min(cap, base * 2 ** (attempt - 1));
    return (delay + this.random() * delay * 0.1) * 1_000;
  }

  private apiError(response: Response, payload: unknown): QDashApiError {
    const options = { statusCode: response.status, payload };
    const message = errorMessage(response, payload);
    if (response.status === 401 || response.status === 403) {
      return new QDashAuthError(message, options);
    }
    if (response.status === 404) return new QDashNotFoundError(message, options);
    if (response.status === 422) return new QDashValidationError(message, options);
    return new QDashTransportError(message, options);
  }
}
