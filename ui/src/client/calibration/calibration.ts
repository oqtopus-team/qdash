/**
 * Generated by orval v7.7.0 🍺
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

import { customInstance } from "../../lib/custom-instance";
import type { ErrorType, BodyType } from "../../lib/custom-instance";

type SecondParameter<T extends (...args: never) => unknown> = Parameters<T>[1];

/**
 * List all the cron schedules.
 * @summary Fetches all the cron schedules.
 */
export const listCronSchedules = (
  options?: SecondParameter<typeof customInstance>,
  signal?: AbortSignal,
) => {
  return customInstance<ListCronScheduleResponse>(
    { url: `/api/calibration/cron-schedule`, method: "GET", signal },
    options,
  );
};

export const getListCronSchedulesQueryKey = () => {
  return [`/api/calibration/cron-schedule`] as const;
};

export const getListCronSchedulesQueryOptions = <
  TData = Awaited<ReturnType<typeof listCronSchedules>>,
  TError = ErrorType<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof listCronSchedules>>,
      TError,
      TData
    >
  >;
  request?: SecondParameter<typeof customInstance>;
}) => {
  const { query: queryOptions, request: requestOptions } = options ?? {};

  const queryKey = queryOptions?.queryKey ?? getListCronSchedulesQueryKey();

  const queryFn: QueryFunction<
    Awaited<ReturnType<typeof listCronSchedules>>
  > = ({ signal }) => listCronSchedules(requestOptions, signal);

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof listCronSchedules>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type ListCronSchedulesQueryResult = NonNullable<
  Awaited<ReturnType<typeof listCronSchedules>>
>;
export type ListCronSchedulesQueryError = ErrorType<unknown>;

export function useListCronSchedules<
  TData = Awaited<ReturnType<typeof listCronSchedules>>,
  TError = ErrorType<unknown>,
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
  request?: SecondParameter<typeof customInstance>;
}): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useListCronSchedules<
  TData = Awaited<ReturnType<typeof listCronSchedules>>,
  TError = ErrorType<unknown>,
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
  request?: SecondParameter<typeof customInstance>;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useListCronSchedules<
  TData = Awaited<ReturnType<typeof listCronSchedules>>,
  TError = ErrorType<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof listCronSchedules>>,
      TError,
      TData
    >
  >;
  request?: SecondParameter<typeof customInstance>;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary Fetches all the cron schedules.
 */

export function useListCronSchedules<
  TData = Awaited<ReturnType<typeof listCronSchedules>>,
  TError = ErrorType<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof listCronSchedules>>,
      TError,
      TData
    >
  >;
  request?: SecondParameter<typeof customInstance>;
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
  scheduleCronCalibRequest: BodyType<ScheduleCronCalibRequest>,
  options?: SecondParameter<typeof customInstance>,
  signal?: AbortSignal,
) => {
  return customInstance<ScheduleCronCalibResponse>(
    {
      url: `/api/calibration/cron-schedule`,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      data: scheduleCronCalibRequest,
      signal,
    },
    options,
  );
};

export const getScheduleCronCalibMutationOptions = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof scheduleCronCalib>>,
    TError,
    { data: BodyType<ScheduleCronCalibRequest> },
    TContext
  >;
  request?: SecondParameter<typeof customInstance>;
}): UseMutationOptions<
  Awaited<ReturnType<typeof scheduleCronCalib>>,
  TError,
  { data: BodyType<ScheduleCronCalibRequest> },
  TContext
> => {
  const mutationKey = ["scheduleCronCalib"];
  const { mutation: mutationOptions, request: requestOptions } = options
    ? options.mutation &&
      "mutationKey" in options.mutation &&
      options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, request: undefined };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof scheduleCronCalib>>,
    { data: BodyType<ScheduleCronCalibRequest> }
  > = (props) => {
    const { data } = props ?? {};

    return scheduleCronCalib(data, requestOptions);
  };

  return { mutationFn, ...mutationOptions };
};

export type ScheduleCronCalibMutationResult = NonNullable<
  Awaited<ReturnType<typeof scheduleCronCalib>>
>;
export type ScheduleCronCalibMutationBody = BodyType<ScheduleCronCalibRequest>;
export type ScheduleCronCalibMutationError = ErrorType<HTTPValidationError>;

/**
 * @summary Schedules a calibration with cron.
 */
export const useScheduleCronCalib = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof scheduleCronCalib>>,
    TError,
    { data: BodyType<ScheduleCronCalibRequest> },
    TContext
  >;
  request?: SecondParameter<typeof customInstance>;
}): UseMutationResult<
  Awaited<ReturnType<typeof scheduleCronCalib>>,
  TError,
  { data: BodyType<ScheduleCronCalibRequest> },
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
  executeCalibRequest: BodyType<ExecuteCalibRequest>,
  options?: SecondParameter<typeof customInstance>,
  signal?: AbortSignal,
) => {
  return customInstance<ExecuteCalibResponse>(
    {
      url: `/api/calibration`,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      data: executeCalibRequest,
      signal,
    },
    options,
  );
};

export const getExecuteCalibMutationOptions = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof executeCalib>>,
    TError,
    { data: BodyType<ExecuteCalibRequest> },
    TContext
  >;
  request?: SecondParameter<typeof customInstance>;
}): UseMutationOptions<
  Awaited<ReturnType<typeof executeCalib>>,
  TError,
  { data: BodyType<ExecuteCalibRequest> },
  TContext
> => {
  const mutationKey = ["executeCalib"];
  const { mutation: mutationOptions, request: requestOptions } = options
    ? options.mutation &&
      "mutationKey" in options.mutation &&
      options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, request: undefined };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof executeCalib>>,
    { data: BodyType<ExecuteCalibRequest> }
  > = (props) => {
    const { data } = props ?? {};

    return executeCalib(data, requestOptions);
  };

  return { mutationFn, ...mutationOptions };
};

export type ExecuteCalibMutationResult = NonNullable<
  Awaited<ReturnType<typeof executeCalib>>
>;
export type ExecuteCalibMutationBody = BodyType<ExecuteCalibRequest>;
export type ExecuteCalibMutationError = ErrorType<HTTPValidationError>;

/**
 * @summary Executes a calibration by creating a flow run from a deployment.
 */
export const useExecuteCalib = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof executeCalib>>,
    TError,
    { data: BodyType<ExecuteCalibRequest> },
    TContext
  >;
  request?: SecondParameter<typeof customInstance>;
}): UseMutationResult<
  Awaited<ReturnType<typeof executeCalib>>,
  TError,
  { data: BodyType<ExecuteCalibRequest> },
  TContext
> => {
  const mutationOptions = getExecuteCalibMutationOptions(options);

  return useMutation(mutationOptions);
};
/**
 * @summary Fetches all the calibration schedules.
 */
export const fetchAllCalibSchedule = (
  options?: SecondParameter<typeof customInstance>,
  signal?: AbortSignal,
) => {
  return customInstance<ScheduleCalibResponse[]>(
    { url: `/api/calibration/schedule`, method: "GET", signal },
    options,
  );
};

export const getFetchAllCalibScheduleQueryKey = () => {
  return [`/api/calibration/schedule`] as const;
};

export const getFetchAllCalibScheduleQueryOptions = <
  TData = Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
  TError = ErrorType<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
      TError,
      TData
    >
  >;
  request?: SecondParameter<typeof customInstance>;
}) => {
  const { query: queryOptions, request: requestOptions } = options ?? {};

  const queryKey = queryOptions?.queryKey ?? getFetchAllCalibScheduleQueryKey();

  const queryFn: QueryFunction<
    Awaited<ReturnType<typeof fetchAllCalibSchedule>>
  > = ({ signal }) => fetchAllCalibSchedule(requestOptions, signal);

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type FetchAllCalibScheduleQueryResult = NonNullable<
  Awaited<ReturnType<typeof fetchAllCalibSchedule>>
>;
export type FetchAllCalibScheduleQueryError = ErrorType<unknown>;

export function useFetchAllCalibSchedule<
  TData = Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
  TError = ErrorType<unknown>,
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
  request?: SecondParameter<typeof customInstance>;
}): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useFetchAllCalibSchedule<
  TData = Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
  TError = ErrorType<unknown>,
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
  request?: SecondParameter<typeof customInstance>;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useFetchAllCalibSchedule<
  TData = Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
  TError = ErrorType<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
      TError,
      TData
    >
  >;
  request?: SecondParameter<typeof customInstance>;
}): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary Fetches all the calibration schedules.
 */

export function useFetchAllCalibSchedule<
  TData = Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
  TError = ErrorType<unknown>,
>(options?: {
  query?: Partial<
    UseQueryOptions<
      Awaited<ReturnType<typeof fetchAllCalibSchedule>>,
      TError,
      TData
    >
  >;
  request?: SecondParameter<typeof customInstance>;
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
  scheduleCalibRequest: BodyType<ScheduleCalibRequest>,
  options?: SecondParameter<typeof customInstance>,
  signal?: AbortSignal,
) => {
  return customInstance<ScheduleCalibResponse>(
    {
      url: `/api/calibration/schedule`,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      data: scheduleCalibRequest,
      signal,
    },
    options,
  );
};

export const getScheduleCalibMutationOptions = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof scheduleCalib>>,
    TError,
    { data: BodyType<ScheduleCalibRequest> },
    TContext
  >;
  request?: SecondParameter<typeof customInstance>;
}): UseMutationOptions<
  Awaited<ReturnType<typeof scheduleCalib>>,
  TError,
  { data: BodyType<ScheduleCalibRequest> },
  TContext
> => {
  const mutationKey = ["scheduleCalib"];
  const { mutation: mutationOptions, request: requestOptions } = options
    ? options.mutation &&
      "mutationKey" in options.mutation &&
      options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, request: undefined };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof scheduleCalib>>,
    { data: BodyType<ScheduleCalibRequest> }
  > = (props) => {
    const { data } = props ?? {};

    return scheduleCalib(data, requestOptions);
  };

  return { mutationFn, ...mutationOptions };
};

export type ScheduleCalibMutationResult = NonNullable<
  Awaited<ReturnType<typeof scheduleCalib>>
>;
export type ScheduleCalibMutationBody = BodyType<ScheduleCalibRequest>;
export type ScheduleCalibMutationError = ErrorType<HTTPValidationError>;

/**
 * @summary Schedules a calibration.
 */
export const useScheduleCalib = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof scheduleCalib>>,
    TError,
    { data: BodyType<ScheduleCalibRequest> },
    TContext
  >;
  request?: SecondParameter<typeof customInstance>;
}): UseMutationResult<
  Awaited<ReturnType<typeof scheduleCalib>>,
  TError,
  { data: BodyType<ScheduleCalibRequest> },
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
  options?: SecondParameter<typeof customInstance>,
) => {
  return customInstance<unknown>(
    { url: `/api/calibration/schedule/${flowRunId}`, method: "DELETE" },
    options,
  );
};

export const getDeleteCalibScheduleMutationOptions = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof deleteCalibSchedule>>,
    TError,
    { flowRunId: string },
    TContext
  >;
  request?: SecondParameter<typeof customInstance>;
}): UseMutationOptions<
  Awaited<ReturnType<typeof deleteCalibSchedule>>,
  TError,
  { flowRunId: string },
  TContext
> => {
  const mutationKey = ["deleteCalibSchedule"];
  const { mutation: mutationOptions, request: requestOptions } = options
    ? options.mutation &&
      "mutationKey" in options.mutation &&
      options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, request: undefined };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof deleteCalibSchedule>>,
    { flowRunId: string }
  > = (props) => {
    const { flowRunId } = props ?? {};

    return deleteCalibSchedule(flowRunId, requestOptions);
  };

  return { mutationFn, ...mutationOptions };
};

export type DeleteCalibScheduleMutationResult = NonNullable<
  Awaited<ReturnType<typeof deleteCalibSchedule>>
>;

export type DeleteCalibScheduleMutationError = ErrorType<HTTPValidationError>;

/**
 * @summary Deletes a calibration schedule.
 */
export const useDeleteCalibSchedule = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof deleteCalibSchedule>>,
    TError,
    { flowRunId: string },
    TContext
  >;
  request?: SecondParameter<typeof customInstance>;
}): UseMutationResult<
  Awaited<ReturnType<typeof deleteCalibSchedule>>,
  TError,
  { flowRunId: string },
  TContext
> => {
  const mutationOptions = getDeleteCalibScheduleMutationOptions(options);

  return useMutation(mutationOptions);
};
