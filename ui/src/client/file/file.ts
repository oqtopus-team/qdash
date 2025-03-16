/**
 * Generated by orval v7.7.0 🍺
 * Do not edit manually.
 * QDash API
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import { useQuery } from "@tanstack/react-query";
import type {
  DataTag,
  DefinedInitialDataOptions,
  DefinedUseQueryResult,
  QueryFunction,
  QueryKey,
  UndefinedInitialDataOptions,
  UseQueryOptions,
  UseQueryResult,
} from "@tanstack/react-query";

import axios from "axios";
import type { AxiosError, AxiosRequestConfig, AxiosResponse } from "axios";

import type { DownloadFileParams, HTTPValidationError } from "../../schemas";

/**
 * Download a file.
 * @summary download file
 */
export const downloadFile = (
  params: DownloadFileParams,
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<void>> => {
  return axios.get(`http://localhost:5715/api/file/raw_data`, {
    ...options,
    params: { ...params, ...options?.params },
  });
};

export const getDownloadFileQueryKey = (params: DownloadFileParams) => {
  return [
    `http://localhost:5715/api/file/raw_data`,
    ...(params ? [params] : []),
  ] as const;
};

export const getDownloadFileQueryOptions = <
  TData = Awaited<ReturnType<typeof downloadFile>>,
  TError = AxiosError<HTTPValidationError>,
>(
  params: DownloadFileParams,
  options?: {
    query?: Partial<
      UseQueryOptions<Awaited<ReturnType<typeof downloadFile>>, TError, TData>
    >;
    axios?: AxiosRequestConfig;
  },
) => {
  const { query: queryOptions, axios: axiosOptions } = options ?? {};

  const queryKey = queryOptions?.queryKey ?? getDownloadFileQueryKey(params);

  const queryFn: QueryFunction<Awaited<ReturnType<typeof downloadFile>>> = ({
    signal,
  }) => downloadFile(params, { signal, ...axiosOptions });

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof downloadFile>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type DownloadFileQueryResult = NonNullable<
  Awaited<ReturnType<typeof downloadFile>>
>;
export type DownloadFileQueryError = AxiosError<HTTPValidationError>;

export function useDownloadFile<
  TData = Awaited<ReturnType<typeof downloadFile>>,
  TError = AxiosError<HTTPValidationError>,
>(
  params: DownloadFileParams,
  options: {
    query: Partial<
      UseQueryOptions<Awaited<ReturnType<typeof downloadFile>>, TError, TData>
    > &
      Pick<
        DefinedInitialDataOptions<
          Awaited<ReturnType<typeof downloadFile>>,
          TError,
          Awaited<ReturnType<typeof downloadFile>>
        >,
        "initialData"
      >;
    axios?: AxiosRequestConfig;
  },
): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useDownloadFile<
  TData = Awaited<ReturnType<typeof downloadFile>>,
  TError = AxiosError<HTTPValidationError>,
>(
  params: DownloadFileParams,
  options?: {
    query?: Partial<
      UseQueryOptions<Awaited<ReturnType<typeof downloadFile>>, TError, TData>
    > &
      Pick<
        UndefinedInitialDataOptions<
          Awaited<ReturnType<typeof downloadFile>>,
          TError,
          Awaited<ReturnType<typeof downloadFile>>
        >,
        "initialData"
      >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useDownloadFile<
  TData = Awaited<ReturnType<typeof downloadFile>>,
  TError = AxiosError<HTTPValidationError>,
>(
  params: DownloadFileParams,
  options?: {
    query?: Partial<
      UseQueryOptions<Awaited<ReturnType<typeof downloadFile>>, TError, TData>
    >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary download file
 */

export function useDownloadFile<
  TData = Awaited<ReturnType<typeof downloadFile>>,
  TError = AxiosError<HTTPValidationError>,
>(
  params: DownloadFileParams,
  options?: {
    query?: Partial<
      UseQueryOptions<Awaited<ReturnType<typeof downloadFile>>, TError, TData>
    >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getDownloadFileQueryOptions(params, options);

  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & {
    queryKey: DataTag<QueryKey, TData>;
  };

  query.queryKey = queryOptions.queryKey;

  return query;
}
