import type { AxiosRequestConfig } from "axios";

import { QDashConfigError } from "./errors.js";
import type { QDashTransport } from "./transport.js";

export interface QDashRequestOptions extends AxiosRequestConfig {
  qdashTransport?: QDashTransport;
}

export async function qdashRequest<T>(
  config: AxiosRequestConfig,
  options: QDashRequestOptions = {},
): Promise<T> {
  const { qdashTransport, ...overrides } = options;
  if (!qdashTransport) {
    throw new QDashConfigError("Generated API calls require a QDashClient transport");
  }
  return qdashTransport.request<T>({ ...config, ...overrides });
}
