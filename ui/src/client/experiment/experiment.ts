/**
 * Generated by orval v7.6.0 🍺
 * Do not edit manually.
 * QDash Server
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

import type { ExperimentResponse } from "../../schemas";

/**
 * @summary Fetch all experiments
 */
export const fetchAllExperiment = (
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<ExperimentResponse[]>> => {
  return axios.get(`http://localhost:5715/experiments`, options);
};

export const getFetchAllExperimentQueryKey = () => {
  return [`http://localhost:5715/experiments`] as const;
};

export const getFetchAllExperimentQueryOptions = <
  TData = Awaited<ReturnType<typeof fetchAllExperiment>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllExperiment>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}) => {
  const { query: queryOptions, axios: axiosOptions } = options ?? {};

  const queryKey = queryOptions?.queryKey ?? getFetchAllExperimentQueryKey();

  const queryFn: QueryFunction<
    Awaited<ReturnType<typeof fetchAllExperiment>>
  > = ({ signal }) => fetchAllExperiment({ signal, ...axiosOptions });

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof fetchAllExperiment>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type FetchAllExperimentQueryResult = NonNullable<
  Awaited<ReturnType<typeof fetchAllExperiment>>
>;
export type FetchAllExperimentQueryError = AxiosError<unknown>;

export function useFetchAllExperiment<
  TData = Awaited<ReturnType<typeof fetchAllExperiment>>,
  TError = AxiosError<unknown>,
>(options: {
  query: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllExperiment>>,
      TError,
      TData
    >
  > &
    Pick<
      DefinedInitialDataOptions<
        Awaited<ReturnType<typeof fetchAllExperiment>>,
        TError,
        Awaited<ReturnType<typeof fetchAllExperiment>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useFetchAllExperiment<
  TData = Awaited<ReturnType<typeof fetchAllExperiment>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllExperiment>>,
      TError,
      TData
    >
  > &
    Pick<
      UndefinedInitialDataOptions<
        Awaited<ReturnType<typeof fetchAllExperiment>>,
        TError,
        Awaited<ReturnType<typeof fetchAllExperiment>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useFetchAllExperiment<
  TData = Awaited<ReturnType<typeof fetchAllExperiment>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllExperiment>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary Fetch all experiments
 */

export function useFetchAllExperiment<
  TData = Awaited<ReturnType<typeof fetchAllExperiment>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllExperiment>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getFetchAllExperimentQueryOptions(options);

  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & {
    queryKey: DataTag<QueryKey, TData>;
  };

  query.queryKey = queryOptions.queryKey;

  return query;
}
