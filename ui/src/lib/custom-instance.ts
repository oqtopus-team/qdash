import Axios, { AxiosHeaders } from "axios";

import type { AxiosError, AxiosRequestConfig, AxiosResponse } from "axios";

export const AXIOS_INSTANCE = Axios.create();

// リクエストインターセプターを追加
AXIOS_INSTANCE.interceptors.request.use((config) => {
  // クッキーからユーザー名を取得
  const username = document.cookie
    .split("; ")
    .find((row) => row.startsWith("username="))
    ?.split("=")[1];

  if (username) {
    // ユーザー名をデコード
    const decodedUsername = decodeURIComponent(username);
    // X-Usernameヘッダーを設定
    if (!config.headers) {
      config.headers = new AxiosHeaders();
    }
    if (config.headers instanceof AxiosHeaders) {
      config.headers.set("X-Username", decodedUsername);
      console.debug(
        "Setting X-Username header:",
        decodedUsername,
        "for URL:",
        config.url,
      );
    }
  }

  return config;
});

export const customInstance = <T>(
  config: AxiosRequestConfig,
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<T>> => {
  const source = Axios.CancelToken.source();
  const promise = AXIOS_INSTANCE({
    ...config,
    ...options,
    cancelToken: source.token,
  }).then((data) => data);

  // @ts-ignore
  promise.cancel = () => {
    source.cancel("Query was cancelled");
  };

  return promise;
};

export type ErrorType<Error> = AxiosError<Error>;

export type BodyType<BodyData> = BodyData;
