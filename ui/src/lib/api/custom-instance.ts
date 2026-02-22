import Axios, { AxiosHeaders } from "axios";

import type { AxiosRequestConfig, AxiosResponse } from "axios";

export const AXIOS_INSTANCE = Axios.create({
  // Use /api proxy route (handled by Next.js rewrites)
  // Falls back to direct API URL for backward compatibility
  baseURL: process.env.NEXT_PUBLIC_API_URL || "/api",
});

// Add request interceptor
AXIOS_INSTANCE.interceptors.request.use((config) => {
  // Get token from cookie
  const token = document.cookie
    .split("; ")
    .find((row) => row.startsWith("access_token="))
    ?.split("=")[1];

  if (token) {
    // Decode token
    const decodedToken = decodeURIComponent(token);
    // Set Authorization: Bearer header
    if (!config.headers) {
      config.headers = new AxiosHeaders();
    }
    if (config.headers instanceof AxiosHeaders) {
      config.headers.set("Authorization", `Bearer ${decodedToken}`);
      console.debug("Setting Authorization header for URL:", config.url);
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
