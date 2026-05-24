import Axios, { AxiosHeaders } from "axios";

import type { AxiosRequestConfig, AxiosResponse } from "axios";

import { getProjectId } from "@/lib/auth/session";

export const AXIOS_INSTANCE = Axios.create({
  // Browser API calls must go through the Next.js route handler so HttpOnly
  // session cookies can be translated into backend Authorization headers.
  baseURL: "/api",
});

// Add request interceptor
AXIOS_INSTANCE.interceptors.request.use((config) => {
  const projectId = getProjectId();

  if (projectId) {
    if (!config.headers) {
      config.headers = new AxiosHeaders();
    }
    if (config.headers instanceof AxiosHeaders) {
      config.headers.set("X-Project-Id", projectId);
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
