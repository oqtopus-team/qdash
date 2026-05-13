import Axios, { AxiosHeaders } from "axios";

import type { AxiosRequestConfig, AxiosResponse } from "axios";

import { getAccessToken, getProjectId } from "@/lib/auth/session";

export const AXIOS_INSTANCE = Axios.create({
  // Use /api proxy route (handled by Next.js rewrites)
  // Falls back to direct API URL for backward compatibility
  baseURL: process.env.NEXT_PUBLIC_API_URL || "/api",
});

// Add request interceptor
AXIOS_INSTANCE.interceptors.request.use((config) => {
  const token = getAccessToken();

  if (token) {
    if (!config.headers) {
      config.headers = new AxiosHeaders();
    }
    if (config.headers instanceof AxiosHeaders) {
      config.headers.set("Authorization", `Bearer ${token}`);
      const projectId = getProjectId();
      if (projectId) {
        config.headers.set("X-Project-Id", projectId);
      }
    }
  }

  return config;
});

interface CancellablePromise<T> extends Promise<T> {
  cancel: () => void;
}

export const customInstance = <T>(
  config: AxiosRequestConfig,
  options?: AxiosRequestConfig,
): CancellablePromise<AxiosResponse<T>> => {
  const source = Axios.CancelToken.source();
  const promise = AXIOS_INSTANCE({
    ...config,
    ...options,
    cancelToken: source.token,
  }).then((data) => data) as CancellablePromise<AxiosResponse<T>>;

  promise.cancel = () => {
    source.cancel("Query was cancelled");
  };

  return promise;
};
