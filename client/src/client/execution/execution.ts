/**
 * Generated by orval v7.5.0 🍺
 * Do not edit manually.
 * QDash Server
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import type {
  DataTag,
  DefinedInitialDataOptions,
  DefinedUseQueryResult,
  MutationFunction,
  QueryFunction,
  QueryKey,
  UndefinedInitialDataOptions,
  UseMutationOptions,
  UseMutationResult,
  UseQueryOptions,
  UseQueryResult,
} from "@tanstack/react-query";
import * as axios from "axios";
import type { AxiosError, AxiosRequestConfig, AxiosResponse } from "axios";
import type {
  Detail,
  ExecutionLockStatusResponse,
  ExecutionResponse,
  ExecutionRunResponse,
  FetchAllExecutionsExperimentsParams,
  FetchFigureByPathParams,
  HTTPValidationError,
} from "../../schemas";

/**
 * @summary Fetch all executions
 */
export const fetchAllExecutions = (
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<ExecutionRunResponse[]>> => {
  return axios.default.get(`http://localhost:5715/executions`, options);
};

export const getFetchAllExecutionsQueryKey = () => {
  return [`http://localhost:5715/executions`] as const;
};

export const getFetchAllExecutionsQueryOptions = <
  TData = Awaited<ReturnType<typeof fetchAllExecutions>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllExecutions>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}) => {
  const { query: queryOptions, axios: axiosOptions } = options ?? {};

  const queryKey = queryOptions?.queryKey ?? getFetchAllExecutionsQueryKey();

  const queryFn: QueryFunction<
    Awaited<ReturnType<typeof fetchAllExecutions>>
  > = ({ signal }) => fetchAllExecutions({ signal, ...axiosOptions });

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof fetchAllExecutions>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type FetchAllExecutionsQueryResult = NonNullable<
  Awaited<ReturnType<typeof fetchAllExecutions>>
>;
export type FetchAllExecutionsQueryError = AxiosError<unknown>;

export function useFetchAllExecutions<
  TData = Awaited<ReturnType<typeof fetchAllExecutions>>,
  TError = AxiosError<unknown>,
>(options: {
  query: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllExecutions>>,
      TError,
      TData
    >
  > &
    Pick<
      DefinedInitialDataOptions<
        Awaited<ReturnType<typeof fetchAllExecutions>>,
        TError,
        Awaited<ReturnType<typeof fetchAllExecutions>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useFetchAllExecutions<
  TData = Awaited<ReturnType<typeof fetchAllExecutions>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllExecutions>>,
      TError,
      TData
    >
  > &
    Pick<
      UndefinedInitialDataOptions<
        Awaited<ReturnType<typeof fetchAllExecutions>>,
        TError,
        Awaited<ReturnType<typeof fetchAllExecutions>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useFetchAllExecutions<
  TData = Awaited<ReturnType<typeof fetchAllExecutions>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllExecutions>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary Fetch all executions
 */

export function useFetchAllExecutions<
  TData = Awaited<ReturnType<typeof fetchAllExecutions>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllExecutions>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getFetchAllExecutionsQueryOptions(options);

  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & {
    queryKey: DataTag<QueryKey, TData>;
  };

  query.queryKey = queryOptions.queryKey;

  return query;
}

/**
 * @summary Fetch an execution by its ID
 */
export const fetchExperimentsById = (
  executionId: string,
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<ExecutionResponse[]>> => {
  return axios.default.get(
    `http://localhost:5715/executions/${executionId}/experiments`,
    options,
  );
};

export const getFetchExperimentsByIdQueryKey = (executionId: string) => {
  return [
    `http://localhost:5715/executions/${executionId}/experiments`,
  ] as const;
};

export const getFetchExperimentsByIdQueryOptions = <
  TData = Awaited<ReturnType<typeof fetchExperimentsById>>,
  TError = AxiosError<HTTPValidationError>,
>(
  executionId: string,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchExperimentsById>>,
        TError,
        TData
      >
    >;
    axios?: AxiosRequestConfig;
  },
) => {
  const { query: queryOptions, axios: axiosOptions } = options ?? {};

  const queryKey =
    queryOptions?.queryKey ?? getFetchExperimentsByIdQueryKey(executionId);

  const queryFn: QueryFunction<
    Awaited<ReturnType<typeof fetchExperimentsById>>
  > = ({ signal }) =>
    fetchExperimentsById(executionId, { signal, ...axiosOptions });

  return {
    queryKey,
    queryFn,
    enabled: !!executionId,
    ...queryOptions,
  } as UseQueryOptions<
    Awaited<ReturnType<typeof fetchExperimentsById>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type FetchExperimentsByIdQueryResult = NonNullable<
  Awaited<ReturnType<typeof fetchExperimentsById>>
>;
export type FetchExperimentsByIdQueryError = AxiosError<HTTPValidationError>;

export function useFetchExperimentsById<
  TData = Awaited<ReturnType<typeof fetchExperimentsById>>,
  TError = AxiosError<HTTPValidationError>,
>(
  executionId: string,
  options: {
    query: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchExperimentsById>>,
        TError,
        TData
      >
    > &
      Pick<
        DefinedInitialDataOptions<
          Awaited<ReturnType<typeof fetchExperimentsById>>,
          TError,
          Awaited<ReturnType<typeof fetchExperimentsById>>
        >,
        "initialData"
      >;
    axios?: AxiosRequestConfig;
  },
): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useFetchExperimentsById<
  TData = Awaited<ReturnType<typeof fetchExperimentsById>>,
  TError = AxiosError<HTTPValidationError>,
>(
  executionId: string,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchExperimentsById>>,
        TError,
        TData
      >
    > &
      Pick<
        UndefinedInitialDataOptions<
          Awaited<ReturnType<typeof fetchExperimentsById>>,
          TError,
          Awaited<ReturnType<typeof fetchExperimentsById>>
        >,
        "initialData"
      >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useFetchExperimentsById<
  TData = Awaited<ReturnType<typeof fetchExperimentsById>>,
  TError = AxiosError<HTTPValidationError>,
>(
  executionId: string,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchExperimentsById>>,
        TError,
        TData
      >
    >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary Fetch an execution by its ID
 */

export function useFetchExperimentsById<
  TData = Awaited<ReturnType<typeof fetchExperimentsById>>,
  TError = AxiosError<HTTPValidationError>,
>(
  executionId: string,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchExperimentsById>>,
        TError,
        TData
      >
    >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getFetchExperimentsByIdQueryOptions(
    executionId,
    options,
  );

  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & {
    queryKey: DataTag<QueryKey, TData>;
  };

  query.queryKey = queryOptions.queryKey;

  return query;
}

/**
 * @summary Add tags to an execution
 */
export const addExecutionTags = (
  executionId: string,
  addExecutionTagsBody: string[],
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<unknown>> => {
  return axios.default.post(
    `http://localhost:5715/executions/${executionId}/tags`,
    addExecutionTagsBody,
    options,
  );
};

export const getAddExecutionTagsMutationOptions = <
  TError = AxiosError<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof addExecutionTags>>,
    TError,
    { executionId: string; data: string[] },
    TContext
  >;
  axios?: AxiosRequestConfig;
}): UseMutationOptions<
  Awaited<ReturnType<typeof addExecutionTags>>,
  TError,
  { executionId: string; data: string[] },
  TContext
> => {
  const mutationKey = ["addExecutionTags"];
  const { mutation: mutationOptions, axios: axiosOptions } = options
    ? options.mutation &&
      "mutationKey" in options.mutation &&
      options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, axios: undefined };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof addExecutionTags>>,
    { executionId: string; data: string[] }
  > = (props) => {
    const { executionId, data } = props ?? {};

    return addExecutionTags(executionId, data, axiosOptions);
  };

  return { mutationFn, ...mutationOptions };
};

export type AddExecutionTagsMutationResult = NonNullable<
  Awaited<ReturnType<typeof addExecutionTags>>
>;
export type AddExecutionTagsMutationBody = string[];
export type AddExecutionTagsMutationError = AxiosError<HTTPValidationError>;

/**
 * @summary Add tags to an execution
 */
export const useAddExecutionTags = <
  TError = AxiosError<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof addExecutionTags>>,
    TError,
    { executionId: string; data: string[] },
    TContext
  >;
  axios?: AxiosRequestConfig;
}): UseMutationResult<
  Awaited<ReturnType<typeof addExecutionTags>>,
  TError,
  { executionId: string; data: string[] },
  TContext
> => {
  const mutationOptions = getAddExecutionTagsMutationOptions(options);

  return useMutation(mutationOptions);
};
/**
 * @summary Remove tags from an execution
 */
export const removeExecutionTags = (
  executionId: string,
  removeExecutionTagsBody: string[],
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<unknown>> => {
  return axios.default.delete(
    `http://localhost:5715/executions/${executionId}/tags`,
    { data: removeExecutionTagsBody, ...options },
  );
};

export const getRemoveExecutionTagsMutationOptions = <
  TError = AxiosError<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof removeExecutionTags>>,
    TError,
    { executionId: string; data: string[] },
    TContext
  >;
  axios?: AxiosRequestConfig;
}): UseMutationOptions<
  Awaited<ReturnType<typeof removeExecutionTags>>,
  TError,
  { executionId: string; data: string[] },
  TContext
> => {
  const mutationKey = ["removeExecutionTags"];
  const { mutation: mutationOptions, axios: axiosOptions } = options
    ? options.mutation &&
      "mutationKey" in options.mutation &&
      options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, axios: undefined };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof removeExecutionTags>>,
    { executionId: string; data: string[] }
  > = (props) => {
    const { executionId, data } = props ?? {};

    return removeExecutionTags(executionId, data, axiosOptions);
  };

  return { mutationFn, ...mutationOptions };
};

export type RemoveExecutionTagsMutationResult = NonNullable<
  Awaited<ReturnType<typeof removeExecutionTags>>
>;
export type RemoveExecutionTagsMutationBody = string[];
export type RemoveExecutionTagsMutationError = AxiosError<HTTPValidationError>;

/**
 * @summary Remove tags from an execution
 */
export const useRemoveExecutionTags = <
  TError = AxiosError<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof removeExecutionTags>>,
    TError,
    { executionId: string; data: string[] },
    TContext
  >;
  axios?: AxiosRequestConfig;
}): UseMutationResult<
  Awaited<ReturnType<typeof removeExecutionTags>>,
  TError,
  { executionId: string; data: string[] },
  TContext
> => {
  const mutationOptions = getRemoveExecutionTagsMutationOptions(options);

  return useMutation(mutationOptions);
};
/**
 * @summary Fetch all executions
 */
export const fetchAllExecutionsExperiments = (
  params?: FetchAllExecutionsExperimentsParams,
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<ExecutionResponse[]>> => {
  return axios.default.get(`http://localhost:5715/executions/experiments`, {
    ...options,
    params: { ...params, ...options?.params },
  });
};

export const getFetchAllExecutionsExperimentsQueryKey = (
  params?: FetchAllExecutionsExperimentsParams,
) => {
  return [
    `http://localhost:5715/executions/experiments`,
    ...(params ? [params] : []),
  ] as const;
};

export const getFetchAllExecutionsExperimentsQueryOptions = <
  TData = Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>,
  TError = AxiosError<HTTPValidationError>,
>(
  params?: FetchAllExecutionsExperimentsParams,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>,
        TError,
        TData
      >
    >;
    axios?: AxiosRequestConfig;
  },
) => {
  const { query: queryOptions, axios: axiosOptions } = options ?? {};

  const queryKey =
    queryOptions?.queryKey ?? getFetchAllExecutionsExperimentsQueryKey(params);

  const queryFn: QueryFunction<
    Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>
  > = ({ signal }) =>
    fetchAllExecutionsExperiments(params, { signal, ...axiosOptions });

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type FetchAllExecutionsExperimentsQueryResult = NonNullable<
  Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>
>;
export type FetchAllExecutionsExperimentsQueryError =
  AxiosError<HTTPValidationError>;

export function useFetchAllExecutionsExperiments<
  TData = Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>,
  TError = AxiosError<HTTPValidationError>,
>(
  params: undefined | FetchAllExecutionsExperimentsParams,
  options: {
    query: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>,
        TError,
        TData
      >
    > &
      Pick<
        DefinedInitialDataOptions<
          Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>,
          TError,
          Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>
        >,
        "initialData"
      >;
    axios?: AxiosRequestConfig;
  },
): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useFetchAllExecutionsExperiments<
  TData = Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>,
  TError = AxiosError<HTTPValidationError>,
>(
  params?: FetchAllExecutionsExperimentsParams,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>,
        TError,
        TData
      >
    > &
      Pick<
        UndefinedInitialDataOptions<
          Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>,
          TError,
          Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>
        >,
        "initialData"
      >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useFetchAllExecutionsExperiments<
  TData = Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>,
  TError = AxiosError<HTTPValidationError>,
>(
  params?: FetchAllExecutionsExperimentsParams,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>,
        TError,
        TData
      >
    >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary Fetch all executions
 */

export function useFetchAllExecutionsExperiments<
  TData = Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>,
  TError = AxiosError<HTTPValidationError>,
>(
  params?: FetchAllExecutionsExperimentsParams,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchAllExecutionsExperiments>>,
        TError,
        TData
      >
    >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getFetchAllExecutionsExperimentsQueryOptions(
    params,
    options,
  );

  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & {
    queryKey: DataTag<QueryKey, TData>;
  };

  query.queryKey = queryOptions.queryKey;

  return query;
}

/**
 * @summary Fetches a calibration figure by its path
 */
export const fetchFigureByPath = (
  params: FetchFigureByPathParams,
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<void>> => {
  return axios.default.get(`http://localhost:5715/executions/figure`, {
    ...options,
    params: { ...params, ...options?.params },
  });
};

export const getFetchFigureByPathQueryKey = (
  params: FetchFigureByPathParams,
) => {
  return [
    `http://localhost:5715/executions/figure`,
    ...(params ? [params] : []),
  ] as const;
};

export const getFetchFigureByPathQueryOptions = <
  TData = Awaited<ReturnType<typeof fetchFigureByPath>>,
  TError = AxiosError<Detail | HTTPValidationError>,
>(
  params: FetchFigureByPathParams,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchFigureByPath>>,
        TError,
        TData
      >
    >;
    axios?: AxiosRequestConfig;
  },
) => {
  const { query: queryOptions, axios: axiosOptions } = options ?? {};

  const queryKey =
    queryOptions?.queryKey ?? getFetchFigureByPathQueryKey(params);

  const queryFn: QueryFunction<
    Awaited<ReturnType<typeof fetchFigureByPath>>
  > = ({ signal }) => fetchFigureByPath(params, { signal, ...axiosOptions });

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof fetchFigureByPath>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type FetchFigureByPathQueryResult = NonNullable<
  Awaited<ReturnType<typeof fetchFigureByPath>>
>;
export type FetchFigureByPathQueryError = AxiosError<
  Detail | HTTPValidationError
>;

export function useFetchFigureByPath<
  TData = Awaited<ReturnType<typeof fetchFigureByPath>>,
  TError = AxiosError<Detail | HTTPValidationError>,
>(
  params: FetchFigureByPathParams,
  options: {
    query: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchFigureByPath>>,
        TError,
        TData
      >
    > &
      Pick<
        DefinedInitialDataOptions<
          Awaited<ReturnType<typeof fetchFigureByPath>>,
          TError,
          Awaited<ReturnType<typeof fetchFigureByPath>>
        >,
        "initialData"
      >;
    axios?: AxiosRequestConfig;
  },
): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useFetchFigureByPath<
  TData = Awaited<ReturnType<typeof fetchFigureByPath>>,
  TError = AxiosError<Detail | HTTPValidationError>,
>(
  params: FetchFigureByPathParams,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchFigureByPath>>,
        TError,
        TData
      >
    > &
      Pick<
        UndefinedInitialDataOptions<
          Awaited<ReturnType<typeof fetchFigureByPath>>,
          TError,
          Awaited<ReturnType<typeof fetchFigureByPath>>
        >,
        "initialData"
      >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useFetchFigureByPath<
  TData = Awaited<ReturnType<typeof fetchFigureByPath>>,
  TError = AxiosError<Detail | HTTPValidationError>,
>(
  params: FetchFigureByPathParams,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchFigureByPath>>,
        TError,
        TData
      >
    >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary Fetches a calibration figure by its path
 */

export function useFetchFigureByPath<
  TData = Awaited<ReturnType<typeof fetchFigureByPath>>,
  TError = AxiosError<Detail | HTTPValidationError>,
>(
  params: FetchFigureByPathParams,
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof fetchFigureByPath>>,
        TError,
        TData
      >
    >;
    axios?: AxiosRequestConfig;
  },
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getFetchFigureByPathQueryOptions(params, options);

  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & {
    queryKey: DataTag<QueryKey, TData>;
  };

  query.queryKey = queryOptions.queryKey;

  return query;
}

/**
 * @summary Fetches the status of a calibration.
 */
export const fetchExecutionLockStatus = (
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<ExecutionLockStatusResponse>> => {
  return axios.default.get(
    `http://localhost:5715/executions/lock_status`,
    options,
  );
};

export const getFetchExecutionLockStatusQueryKey = () => {
  return [`http://localhost:5715/executions/lock_status`] as const;
};

export const getFetchExecutionLockStatusQueryOptions = <
  TData = Awaited<ReturnType<typeof fetchExecutionLockStatus>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchExecutionLockStatus>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}) => {
  const { query: queryOptions, axios: axiosOptions } = options ?? {};

  const queryKey =
    queryOptions?.queryKey ?? getFetchExecutionLockStatusQueryKey();

  const queryFn: QueryFunction<
    Awaited<ReturnType<typeof fetchExecutionLockStatus>>
  > = ({ signal }) => fetchExecutionLockStatus({ signal, ...axiosOptions });

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof fetchExecutionLockStatus>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type FetchExecutionLockStatusQueryResult = NonNullable<
  Awaited<ReturnType<typeof fetchExecutionLockStatus>>
>;
export type FetchExecutionLockStatusQueryError = AxiosError<unknown>;

export function useFetchExecutionLockStatus<
  TData = Awaited<ReturnType<typeof fetchExecutionLockStatus>>,
  TError = AxiosError<unknown>,
>(options: {
  query: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchExecutionLockStatus>>,
      TError,
      TData
    >
  > &
    Pick<
      DefinedInitialDataOptions<
        Awaited<ReturnType<typeof fetchExecutionLockStatus>>,
        TError,
        Awaited<ReturnType<typeof fetchExecutionLockStatus>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useFetchExecutionLockStatus<
  TData = Awaited<ReturnType<typeof fetchExecutionLockStatus>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchExecutionLockStatus>>,
      TError,
      TData
    >
  > &
    Pick<
      UndefinedInitialDataOptions<
        Awaited<ReturnType<typeof fetchExecutionLockStatus>>,
        TError,
        Awaited<ReturnType<typeof fetchExecutionLockStatus>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useFetchExecutionLockStatus<
  TData = Awaited<ReturnType<typeof fetchExecutionLockStatus>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchExecutionLockStatus>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary Fetches the status of a calibration.
 */

export function useFetchExecutionLockStatus<
  TData = Awaited<ReturnType<typeof fetchExecutionLockStatus>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchExecutionLockStatus>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getFetchExecutionLockStatusQueryOptions(options);

  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & {
    queryKey: DataTag<QueryKey, TData>;
  };

  query.queryKey = queryOptions.queryKey;

  return query;
}
