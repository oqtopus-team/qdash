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

import type { ListTaskResponse } from "../../schemas";

/**
 * Fetch all tasks.

Args:
----
    current_user (User): The current user.

Returns:
-------
    list[TaskResponse]: The list of tasks.
 * @summary Fetch all tasks
 */
export const fetchAllTasks = (
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<ListTaskResponse>> => {
  return axios.get(`http://localhost:5715/api/tasks`, options);
};

export const getFetchAllTasksQueryKey = () => {
  return [`http://localhost:5715/api/tasks`] as const;
};

export const getFetchAllTasksQueryOptions = <
  TData = Awaited<ReturnType<typeof fetchAllTasks>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<Awaited<ReturnType<typeof fetchAllTasks>>, TError, TData>
  >;
  axios?: AxiosRequestConfig;
}) => {
  const { query: queryOptions, axios: axiosOptions } = options ?? {};

  const queryKey = queryOptions?.queryKey ?? getFetchAllTasksQueryKey();

  const queryFn: QueryFunction<Awaited<ReturnType<typeof fetchAllTasks>>> = ({
    signal,
  }) => fetchAllTasks({ signal, ...axiosOptions });

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof fetchAllTasks>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type FetchAllTasksQueryResult = NonNullable<
  Awaited<ReturnType<typeof fetchAllTasks>>
>;
export type FetchAllTasksQueryError = AxiosError<unknown>;

export function useFetchAllTasks<
  TData = Awaited<ReturnType<typeof fetchAllTasks>>,
  TError = AxiosError<unknown>,
>(options: {
  query: Partial<
    UseQueryOptions<Awaited<ReturnType<typeof fetchAllTasks>>, TError, TData>
  > &
    Pick<
      DefinedInitialDataOptions<
        Awaited<ReturnType<typeof fetchAllTasks>>,
        TError,
        Awaited<ReturnType<typeof fetchAllTasks>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useFetchAllTasks<
  TData = Awaited<ReturnType<typeof fetchAllTasks>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<Awaited<ReturnType<typeof fetchAllTasks>>, TError, TData>
  > &
    Pick<
      UndefinedInitialDataOptions<
        Awaited<ReturnType<typeof fetchAllTasks>>,
        TError,
        Awaited<ReturnType<typeof fetchAllTasks>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useFetchAllTasks<
  TData = Awaited<ReturnType<typeof fetchAllTasks>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<Awaited<ReturnType<typeof fetchAllTasks>>, TError, TData>
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary Fetch all tasks
 */

export function useFetchAllTasks<
  TData = Awaited<ReturnType<typeof fetchAllTasks>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<Awaited<ReturnType<typeof fetchAllTasks>>, TError, TData>
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getFetchAllTasksQueryOptions(options);

  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & {
    queryKey: DataTag<QueryKey, TData>;
  };

  query.queryKey = queryOptions.queryKey;

  return query;
}
