/**
 * Generated by orval v7.6.0 🍺
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

import type {
  FridgesGetFridgeTemperatureParams,
  HTTPValidationError,
  ListAllFridgeResponse,
  ListFridgeResponse,
} from "../../schemas";

/**
 * @summary List All Fridges
 */
export const fridgesListAllFridges = (
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<ListAllFridgeResponse>> => {
  return axios.get(`http://localhost:5715/fridges/`, options);
};

export const getFridgesListAllFridgesQueryKey = () => {
  return [`http://localhost:5715/fridges/`] as const;
};

export const getFridgesListAllFridgesQueryOptions = <
  TData = Awaited<ReturnType<typeof fridgesListAllFridges>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fridgesListAllFridges>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}) => {
  const { query: queryOptions, axios: axiosOptions } = options ?? {};

  const queryKey = queryOptions?.queryKey ?? getFridgesListAllFridgesQueryKey();

  const queryFn: QueryFunction<
    Awaited<ReturnType<typeof fridgesListAllFridges>>
  > = ({ signal }) => fridgesListAllFridges({ signal, ...axiosOptions });

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof fridgesListAllFridges>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type FridgesListAllFridgesQueryResult = NonNullable<
  Awaited<ReturnType<typeof fridgesListAllFridges>>
>;
export type FridgesListAllFridgesQueryError = AxiosError<unknown>;

export function useFridgesListAllFridges<
  TData = Awaited<ReturnType<typeof fridgesListAllFridges>>,
  TError = AxiosError<unknown>,
>(options: {
  query: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fridgesListAllFridges>>,
      TError,
      TData
    >
  > &
    Pick<
      DefinedInitialDataOptions<
        Awaited<ReturnType<typeof fridgesListAllFridges>>,
        TError,
        Awaited<ReturnType<typeof fridgesListAllFridges>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useFridgesListAllFridges<
  TData = Awaited<ReturnType<typeof fridgesListAllFridges>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fridgesListAllFridges>>,
      TError,
      TData
    >
  > &
    Pick<
      UndefinedInitialDataOptions<
        Awaited<ReturnType<typeof fridgesListAllFridges>>,
        TError,
        Awaited<ReturnType<typeof fridgesListAllFridges>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useFridgesListAllFridges<
  TData = Awaited<ReturnType<typeof fridgesListAllFridges>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fridgesListAllFridges>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary List All Fridges
 */

export function useFridgesListAllFridges<
  TData = Awaited<ReturnType<typeof fridgesListAllFridges>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fridgesListAllFridges>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getFridgesListAllFridgesQueryOptions(options);

  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & {
    queryKey: DataTag<QueryKey, TData>;
  };

  query.queryKey = queryOptions.queryKey;

  return query;
}

/**
 * @summary Get Fridge Temperature
 */
export const fridgesGetFridgeTemperature = (
  channel: number,
  params?: FridgesGetFridgeTemperatureParams,
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<ListFridgeResponse[]>> => {
  return axios.get(`http://localhost:5715/fridges/XLD/channels/${channel}`, {
    ...options,
    params: { ...params, ...options?.params },
  });
};

export const getFridgesGetFridgeTemperatureQueryKey = (
  channel: number,
  params?: FridgesGetFridgeTemperatureParams,
) => {
  return [
    `http://localhost:5715/fridges/XLD/channels/${channel}`,
    ...(params ? [params] : []),
  ] as const;
};

export const getFridgesGetFridgeTemperatureQueryOptions = <
  TData = Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>,
  TError = AxiosError<HTTPValidationError>,
>(
  channel: number,
  params?: FridgesGetFridgeTemperatureParams,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>,
        TError,
        TData
      >
    >;
    axios?: AxiosRequestConfig;
  },
) => {
  const { query: queryOptions, axios: axiosOptions } = options ?? {};

  const queryKey =
    queryOptions?.queryKey ??
    getFridgesGetFridgeTemperatureQueryKey(channel, params);

  const queryFn: QueryFunction<
    Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>
  > = ({ signal }) =>
    fridgesGetFridgeTemperature(channel, params, { signal, ...axiosOptions });

  return {
    queryKey,
    queryFn,
    enabled: !!channel,
    ...queryOptions,
  } as UseQueryOptions<
    Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type FridgesGetFridgeTemperatureQueryResult = NonNullable<
  Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>
>;
export type FridgesGetFridgeTemperatureQueryError =
  AxiosError<HTTPValidationError>;

export function useFridgesGetFridgeTemperature<
  TData = Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>,
  TError = AxiosError<HTTPValidationError>,
>(
  channel: number,
  params: undefined | FridgesGetFridgeTemperatureParams,
  options: {
    query: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>,
        TError,
        TData
      >
    > &
      Pick<
        DefinedInitialDataOptions<
          Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>,
          TError,
          Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>
        >,
        "initialData"
      >;
    axios?: AxiosRequestConfig;
  },
): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useFridgesGetFridgeTemperature<
  TData = Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>,
  TError = AxiosError<HTTPValidationError>,
>(
  channel: number,
  params?: FridgesGetFridgeTemperatureParams,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>,
        TError,
        TData
      >
    > &
      Pick<
        UndefinedInitialDataOptions<
          Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>,
          TError,
          Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>
        >,
        "initialData"
      >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useFridgesGetFridgeTemperature<
  TData = Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>,
  TError = AxiosError<HTTPValidationError>,
>(
  channel: number,
  params?: FridgesGetFridgeTemperatureParams,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>,
        TError,
        TData
      >
    >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary Get Fridge Temperature
 */

export function useFridgesGetFridgeTemperature<
  TData = Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>,
  TError = AxiosError<HTTPValidationError>,
>(
  channel: number,
  params?: FridgesGetFridgeTemperatureParams,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fridgesGetFridgeTemperature>>,
        TError,
        TData
      >
    >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getFridgesGetFridgeTemperatureQueryOptions(
    channel,
    params,
    options,
  );

  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & {
    queryKey: DataTag<QueryKey, TData>;
  };

  query.queryKey = queryOptions.queryKey;

  return query;
}
