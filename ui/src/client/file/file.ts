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

import type { DownloadFileParams, HTTPValidationError } from "../../schemas";

import { customInstance } from "../../lib/custom-instance";
import type { ErrorType } from "../../lib/custom-instance";

type SecondParameter<T extends (...args: never) => unknown> = Parameters<T>[1];

/**
 * Download a file.
 * @summary download file
 */
export const downloadFile = (
  params: DownloadFileParams,
  options?: SecondParameter<typeof customInstance>,
  signal?: AbortSignal,
) => {
  return customInstance<void>(
    { url: `/api/file/raw_data`, method: "GET", params, signal },
    options,
  );
};

export const getDownloadFileQueryKey = (params: DownloadFileParams) => {
  return [`/api/file/raw_data`, ...(params ? [params] : [])] as const;
};

export const getDownloadFileQueryOptions = <
  TData = Awaited<ReturnType<typeof downloadFile>>,
  TError = ErrorType<HTTPValidationError>,
>(
  params: DownloadFileParams,
  options?: {
    query?: Partial<
      UseQueryOptions<Awaited<ReturnType<typeof downloadFile>>, TError, TData>
    >;
    request?: SecondParameter<typeof customInstance>;
  },
) => {
  const { query: queryOptions, request: requestOptions } = options ?? {};

  const queryKey = queryOptions?.queryKey ?? getDownloadFileQueryKey(params);

  const queryFn: QueryFunction<Awaited<ReturnType<typeof downloadFile>>> = ({
    signal,
  }) => downloadFile(params, requestOptions, signal);

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof downloadFile>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type DownloadFileQueryResult = NonNullable<
  Awaited<ReturnType<typeof downloadFile>>
>;
export type DownloadFileQueryError = ErrorType<HTTPValidationError>;

export function useDownloadFile<
  TData = Awaited<ReturnType<typeof downloadFile>>,
  TError = ErrorType<HTTPValidationError>,
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
    request?: SecondParameter<typeof customInstance>;
  },
): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useDownloadFile<
  TData = Awaited<ReturnType<typeof downloadFile>>,
  TError = ErrorType<HTTPValidationError>,
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
    request?: SecondParameter<typeof customInstance>;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useDownloadFile<
  TData = Awaited<ReturnType<typeof downloadFile>>,
  TError = ErrorType<HTTPValidationError>,
>(
  params: DownloadFileParams,
  options?: {
    query?: Partial<
      UseQueryOptions<Awaited<ReturnType<typeof downloadFile>>, TError, TData>
    >;
    request?: SecondParameter<typeof customInstance>;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary download file
 */

export function useDownloadFile<
  TData = Awaited<ReturnType<typeof downloadFile>>,
  TError = ErrorType<HTTPValidationError>,
>(
  params: DownloadFileParams,
  options?: {
    query?: Partial<
      UseQueryOptions<Awaited<ReturnType<typeof downloadFile>>, TError, TData>
    >;
    request?: SecondParameter<typeof customInstance>;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getDownloadFileQueryOptions(params, options);

  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & {
    queryKey: DataTag<QueryKey, TData>;
  };

  query.queryKey = queryOptions.queryKey;

  return query;
}
