/**
 * Generated by orval v7.6.0 🍺
 * Do not edit manually.
 * QDash API
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

import axios from "axios";
import type { AxiosError, AxiosRequestConfig, AxiosResponse } from "axios";

import type {
  ExecuteCalibRequest,
  ExecuteCalibResponse,
  HTTPValidationError,
  ListCronScheduleResponse,
  ScheduleCalibRequest,
  ScheduleCalibResponse,
  ScheduleCronCalibRequest,
  ScheduleCronCalibResponse,
} from "../../schemas";

/**
 * List all the cron schedules.
 * @summary Fetches all the cron schedules.
 */
export const listCronSchedules = (
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<ListCronScheduleResponse>> => {
  return axios.get(
    `http://localhost:5715/api/calibration/cron-schedule`,
    options,
  );
};

export const getListCronSchedulesQueryKey = () => {
  return [`http://localhost:5715/api/calibration/cron-schedule`] as const;
};

export const getListCronSchedulesQueryOptions = <
  TData = Awaited<ReturnType<typeof listCronSchedules>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof listCronSchedules>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}) => {
  const { query: queryOptions, axios: axiosOptions } = options ?? {};

  const queryKey = queryOptions?.queryKey ?? getListCronSchedulesQueryKey();

  const queryFn: QueryFunction<
    Awaited<ReturnType<typeof listCronSchedules>>
  > = ({ signal }) => listCronSchedules({ signal, ...axiosOptions });

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof listCronSchedules>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type ListCronSchedulesQueryResult = NonNullable<
  Awaited<ReturnType<typeof listCronSchedules>>
>;
export type ListCronSchedulesQueryError = AxiosError<unknown>;

export function useListCronSchedules<
  TData = Awaited<ReturnType<typeof listCronSchedules>>,
  TError = AxiosError<unknown>,
>(options: {
  query: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof listCronSchedules>>,
      TError,
      TData
    >
  > &
    Pick<
      DefinedInitialDataOptions<
        Awaited<ReturnType<typeof listCronSchedules>>,
        TError,
        Awaited<ReturnType<typeof listCronSchedules>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useListCronSchedules<
  TData = Awaited<ReturnType<typeof listCronSchedules>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof listCronSchedules>>,
      TError,
      TData
    >
  > &
    Pick<
      UndefinedInitialDataOptions<
        Awaited<ReturnType<typeof listCronSchedules>>,
        TError,
        Awaited<ReturnType<typeof listCronSchedules>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useListCronSchedules<
  TData = Awaited<ReturnType<typeof listCronSchedules>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof listCronSchedules>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary Fetches all the cron schedules.
 */

export function useListCronSchedules<
  TData = Awaited<ReturnType<typeof listCronSchedules>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof listCronSchedules>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getListCronSchedulesQueryOptions(options);

  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & {
    queryKey: DataTag<QueryKey, TData>;
  };

  query.queryKey = queryOptions.queryKey;

  return query;
}

/**
 * Schedule a calibration.
 * @summary Schedules a calibration with cron.
 */
export const scheduleCronCalib = (
  scheduleCronCalibRequest: ScheduleCronCalibRequest,
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<ScheduleCronCalibResponse>> => {
  return axios.post(
    `http://localhost:5715/api/calibration/cron-schedule`,
    scheduleCronCalibRequest,
    options,
  );
};

export const getScheduleCronCalibMutationOptions = <
  TError = AxiosError<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof scheduleCronCalib>>,
    TError,
    { data: ScheduleCronCalibRequest },
    TContext
  >;
  axios?: AxiosRequestConfig;
}): UseMutationOptions<
  Awaited<ReturnType<typeof scheduleCronCalib>>,
  TError,
  { data: ScheduleCronCalibRequest },
  TContext
> => {
  const mutationKey = ["scheduleCronCalib"];
  const { mutation: mutationOptions, axios: axiosOptions } = options
    ? options.mutation &&
      "mutationKey" in options.mutation &&
      options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, axios: undefined };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof scheduleCronCalib>>,
    { data: ScheduleCronCalibRequest }
  > = (props) => {
    const { data } = props ?? {};

    return scheduleCronCalib(data, axiosOptions);
  };

  return { mutationFn, ...mutationOptions };
};

export type ScheduleCronCalibMutationResult = NonNullable<
  Awaited<ReturnType<typeof scheduleCronCalib>>
>;
export type ScheduleCronCalibMutationBody = ScheduleCronCalibRequest;
export type ScheduleCronCalibMutationError = AxiosError<HTTPValidationError>;

/**
 * @summary Schedules a calibration with cron.
 */
export const useScheduleCronCalib = <
  TError = AxiosError<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof scheduleCronCalib>>,
    TError,
    { data: ScheduleCronCalibRequest },
    TContext
  >;
  axios?: AxiosRequestConfig;
}): UseMutationResult<
  Awaited<ReturnType<typeof scheduleCronCalib>>,
  TError,
  { data: ScheduleCronCalibRequest },
  TContext
> => {
  const mutationOptions = getScheduleCronCalibMutationOptions(options);

  return useMutation(mutationOptions);
};
/**
 * Create a flow run from a deployment.
 * @summary Executes a calibration by creating a flow run from a deployment.
 */
export const executeCalib = (
  executeCalibRequest: ExecuteCalibRequest,
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<ExecuteCalibResponse>> => {
  return axios.post(
    `http://localhost:5715/api/calibration`,
    executeCalibRequest,
    options,
  );
};

export const getExecuteCalibMutationOptions = <
  TError = AxiosError<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof executeCalib>>,
    TError,
    { data: ExecuteCalibRequest },
    TContext
  >;
  axios?: AxiosRequestConfig;
}): UseMutationOptions<
  Awaited<ReturnType<typeof executeCalib>>,
  TError,
  { data: ExecuteCalibRequest },
  TContext
> => {
  const mutationKey = ["executeCalib"];
  const { mutation: mutationOptions, axios: axiosOptions } = options
    ? options.mutation &&
      "mutationKey" in options.mutation &&
      options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, axios: undefined };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof executeCalib>>,
    { data: ExecuteCalibRequest }
  > = (props) => {
    const { data } = props ?? {};

    return executeCalib(data, axiosOptions);
  };

  return { mutationFn, ...mutationOptions };
};

export type ExecuteCalibMutationResult = NonNullable<
  Awaited<ReturnType<typeof executeCalib>>
>;
export type ExecuteCalibMutationBody = ExecuteCalibRequest;
export type ExecuteCalibMutationError = AxiosError<HTTPValidationError>;

/**
 * @summary Executes a calibration by creating a flow run from a deployment.
 */
export const useExecuteCalib = <
  TError = AxiosError<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof executeCalib>>,
    TError,
    { data: ExecuteCalibRequest },
    TContext
  >;
  axios?: AxiosRequestConfig;
}): UseMutationResult<
  Awaited<ReturnType<typeof executeCalib>>,
  TError,
  { data: ExecuteCalibRequest },
  TContext
> => {
  const mutationOptions = getExecuteCalibMutationOptions(options);

  return useMutation(mutationOptions);
};
/**
 * @summary Fetches all the calibration schedules.
 */
export const fetchAllCalibSchedule = (
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<ScheduleCalibResponse[]>> => {
  return axios.get(`http://localhost:5715/api/calibration/schedule`, options);
};

export const getFetchAllCalibScheduleQueryKey = () => {
  return [`http://localhost:5715/api/calibration/schedule`] as const;
};

export const getFetchAllCalibScheduleQueryOptions = <
  TData = Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}) => {
  const { query: queryOptions, axios: axiosOptions } = options ?? {};

  const queryKey = queryOptions?.queryKey ?? getFetchAllCalibScheduleQueryKey();

  const queryFn: QueryFunction<
    Awaited<ReturnType<typeof fetchAllCalibSchedule>>
  > = ({ signal }) => fetchAllCalibSchedule({ signal, ...axiosOptions });

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type FetchAllCalibScheduleQueryResult = NonNullable<
  Awaited<ReturnType<typeof fetchAllCalibSchedule>>
>;
export type FetchAllCalibScheduleQueryError = AxiosError<unknown>;

export function useFetchAllCalibSchedule<
  TData = Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
  TError = AxiosError<unknown>,
>(options: {
  query: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
      TError,
      TData
    >
  > &
    Pick<
      DefinedInitialDataOptions<
        Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
        TError,
        Awaited<ReturnType<typeof fetchAllCalibSchedule>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useFetchAllCalibSchedule<
  TData = Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
      TError,
      TData
    >
  > &
    Pick<
      UndefinedInitialDataOptions<
        Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
        TError,
        Awaited<ReturnType<typeof fetchAllCalibSchedule>>
      >,
      "initialData"
    >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useFetchAllCalibSchedule<
  TData = Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary Fetches all the calibration schedules.
 */

export function useFetchAllCalibSchedule<
  TData = Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
  TError = AxiosError<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
      TError,
      TData
    >
  >;
  axios?: AxiosRequestConfig;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getFetchAllCalibScheduleQueryOptions(options);

  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & {
    queryKey: DataTag<QueryKey, TData>;
  };

  query.queryKey = queryOptions.queryKey;

  return query;
}

/**
 * Schedule a calibration.
 * @summary Schedules a calibration.
 */
export const scheduleCalib = (
  scheduleCalibRequest: ScheduleCalibRequest,
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<ScheduleCalibResponse>> => {
  return axios.post(
    `http://localhost:5715/api/calibration/schedule`,
    scheduleCalibRequest,
    options,
  );
};

export const getScheduleCalibMutationOptions = <
  TError = AxiosError<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof scheduleCalib>>,
    TError,
    { data: ScheduleCalibRequest },
    TContext
  >;
  axios?: AxiosRequestConfig;
}): UseMutationOptions<
  Awaited<ReturnType<typeof scheduleCalib>>,
  TError,
  { data: ScheduleCalibRequest },
  TContext
> => {
  const mutationKey = ["scheduleCalib"];
  const { mutation: mutationOptions, axios: axiosOptions } = options
    ? options.mutation &&
      "mutationKey" in options.mutation &&
      options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, axios: undefined };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof scheduleCalib>>,
    { data: ScheduleCalibRequest }
  > = (props) => {
    const { data } = props ?? {};

    return scheduleCalib(data, axiosOptions);
  };

  return { mutationFn, ...mutationOptions };
};

export type ScheduleCalibMutationResult = NonNullable<
  Awaited<ReturnType<typeof scheduleCalib>>
>;
export type ScheduleCalibMutationBody = ScheduleCalibRequest;
export type ScheduleCalibMutationError = AxiosError<HTTPValidationError>;

/**
 * @summary Schedules a calibration.
 */
export const useScheduleCalib = <
  TError = AxiosError<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof scheduleCalib>>,
    TError,
    { data: ScheduleCalibRequest },
    TContext
  >;
  axios?: AxiosRequestConfig;
}): UseMutationResult<
  Awaited<ReturnType<typeof scheduleCalib>>,
  TError,
  { data: ScheduleCalibRequest },
  TContext
> => {
  const mutationOptions = getScheduleCalibMutationOptions(options);

  return useMutation(mutationOptions);
};
/**
 * @summary Deletes a calibration schedule.
 */
export const deleteCalibSchedule = (
  flowRunId: string,
  options?: AxiosRequestConfig,
): Promise<AxiosResponse<unknown>> => {
  return axios.delete(
    `http://localhost:5715/api/calibration/schedule/${flowRunId}`,
    options,
  );
};

export const getDeleteCalibScheduleMutationOptions = <
  TError = AxiosError<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof deleteCalibSchedule>>,
    TError,
    { flowRunId: string },
    TContext
  >;
  axios?: AxiosRequestConfig;
}): UseMutationOptions<
  Awaited<ReturnType<typeof deleteCalibSchedule>>,
  TError,
  { flowRunId: string },
  TContext
> => {
  const mutationKey = ["deleteCalibSchedule"];
  const { mutation: mutationOptions, axios: axiosOptions } = options
    ? options.mutation &&
      "mutationKey" in options.mutation &&
      options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, axios: undefined };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof deleteCalibSchedule>>,
    { flowRunId: string }
  > = (props) => {
    const { flowRunId } = props ?? {};

    return deleteCalibSchedule(flowRunId, axiosOptions);
  };

  return { mutationFn, ...mutationOptions };
};

export type DeleteCalibScheduleMutationResult = NonNullable<
  Awaited<ReturnType<typeof deleteCalibSchedule>>
>;

export type DeleteCalibScheduleMutationError = AxiosError<HTTPValidationError>;

/**
 * @summary Deletes a calibration schedule.
 */
export const useDeleteCalibSchedule = <
  TError = AxiosError<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof deleteCalibSchedule>>,
    TError,
    { flowRunId: string },
    TContext
  >;
  axios?: AxiosRequestConfig;
}): UseMutationResult<
  Awaited<ReturnType<typeof deleteCalibSchedule>>,
  TError,
  { flowRunId: string },
  TContext
> => {
  const mutationOptions = getDeleteCalibScheduleMutationOptions(options);

  return useMutation(mutationOptions);
};
