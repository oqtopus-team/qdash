/**
 * Generated by orval v7.8.0 🍺
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
  QueryClient,
  QueryFunction,
  QueryKey,
  UndefinedInitialDataOptions,
  UseMutationOptions,
  UseMutationResult,
  UseQueryOptions,
  UseQueryResult,
} from "@tanstack/react-query";

import type {
  BodyAuthLoginForAccessToken,
  HTTPValidationError,
  Token,
  User,
  UserCreate,
} from "../../schemas";

import { customInstance } from "../../lib/custom-instance";
import type { ErrorType, BodyType } from "../../lib/custom-instance";

type SecondParameter<T extends (...args: never) => unknown> = Parameters<T>[1];

/**
 * @summary Login For Access Token
 */
export const authLoginForAccessToken = (
  bodyAuthLoginForAccessToken: BodyType<BodyAuthLoginForAccessToken>,
  options?: SecondParameter<typeof customInstance>,
  signal?: AbortSignal,
) => {
  const formUrlEncoded = new URLSearchParams();
  formUrlEncoded.append("username", bodyAuthLoginForAccessToken.username);
  formUrlEncoded.append("password", bodyAuthLoginForAccessToken.password);
  if (bodyAuthLoginForAccessToken.grant_type !== undefined) {
    formUrlEncoded.append("grant_type", bodyAuthLoginForAccessToken.grant_type);
  }

  return customInstance<Token>(
    {
      url: `/api/auth/token`,
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      data: formUrlEncoded,
      signal,
    },
    options,
  );
};

export const getAuthLoginForAccessTokenMutationOptions = <
  TError = ErrorType<void | HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof authLoginForAccessToken>>,
    TError,
    { data: BodyType<BodyAuthLoginForAccessToken> },
    TContext
  >;
  request?: SecondParameter<typeof customInstance>;
}): UseMutationOptions<
  Awaited<ReturnType<typeof authLoginForAccessToken>>,
  TError,
  { data: BodyType<BodyAuthLoginForAccessToken> },
  TContext
> => {
  const mutationKey = ["authLoginForAccessToken"];
  const { mutation: mutationOptions, request: requestOptions } = options
    ? options.mutation &&
      "mutationKey" in options.mutation &&
      options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, request: undefined };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof authLoginForAccessToken>>,
    { data: BodyType<BodyAuthLoginForAccessToken> }
  > = (props) => {
    const { data } = props ?? {};

    return authLoginForAccessToken(data, requestOptions);
  };

  return { mutationFn, ...mutationOptions };
};

export type AuthLoginForAccessTokenMutationResult = NonNullable<
  Awaited<ReturnType<typeof authLoginForAccessToken>>
>;
export type AuthLoginForAccessTokenMutationBody =
  BodyType<BodyAuthLoginForAccessToken>;
export type AuthLoginForAccessTokenMutationError =
  ErrorType<void | HTTPValidationError>;

/**
 * @summary Login For Access Token
 */
export const useAuthLoginForAccessToken = <
  TError = ErrorType<void | HTTPValidationError>,
  TContext = unknown,
>(
  options?: {
    mutation?: UseMutationOptions<
      Awaited<ReturnType<typeof authLoginForAccessToken>>,
      TError,
      { data: BodyType<BodyAuthLoginForAccessToken> },
      TContext
    >;
    request?: SecondParameter<typeof customInstance>;
  },
  queryClient?: QueryClient,
): UseMutationResult<
  Awaited<ReturnType<typeof authLoginForAccessToken>>,
  TError,
  { data: BodyType<BodyAuthLoginForAccessToken> },
  TContext
> => {
  const mutationOptions = getAuthLoginForAccessTokenMutationOptions(options);

  return useMutation(mutationOptions, queryClient);
};
/**
 * @summary Register User
 */
export const authRegisterUser = (
  userCreate: BodyType<UserCreate>,
  options?: SecondParameter<typeof customInstance>,
  signal?: AbortSignal,
) => {
  return customInstance<User>(
    {
      url: `/api/auth/register`,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      data: userCreate,
      signal,
    },
    options,
  );
};

export const getAuthRegisterUserMutationOptions = <
  TError = ErrorType<void | HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof authRegisterUser>>,
    TError,
    { data: BodyType<UserCreate> },
    TContext
  >;
  request?: SecondParameter<typeof customInstance>;
}): UseMutationOptions<
  Awaited<ReturnType<typeof authRegisterUser>>,
  TError,
  { data: BodyType<UserCreate> },
  TContext
> => {
  const mutationKey = ["authRegisterUser"];
  const { mutation: mutationOptions, request: requestOptions } = options
    ? options.mutation &&
      "mutationKey" in options.mutation &&
      options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, request: undefined };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof authRegisterUser>>,
    { data: BodyType<UserCreate> }
  > = (props) => {
    const { data } = props ?? {};

    return authRegisterUser(data, requestOptions);
  };

  return { mutationFn, ...mutationOptions };
};

export type AuthRegisterUserMutationResult = NonNullable<
  Awaited<ReturnType<typeof authRegisterUser>>
>;
export type AuthRegisterUserMutationBody = BodyType<UserCreate>;
export type AuthRegisterUserMutationError =
  ErrorType<void | HTTPValidationError>;

/**
 * @summary Register User
 */
export const useAuthRegisterUser = <
  TError = ErrorType<void | HTTPValidationError>,
  TContext = unknown,
>(
  options?: {
    mutation?: UseMutationOptions<
      Awaited<ReturnType<typeof authRegisterUser>>,
      TError,
      { data: BodyType<UserCreate> },
      TContext
    >;
    request?: SecondParameter<typeof customInstance>;
  },
  queryClient?: QueryClient,
): UseMutationResult<
  Awaited<ReturnType<typeof authRegisterUser>>,
  TError,
  { data: BodyType<UserCreate> },
  TContext
> => {
  const mutationOptions = getAuthRegisterUserMutationOptions(options);

  return useMutation(mutationOptions, queryClient);
};
/**
 * @summary Read Users Me
 */
export const authReadUsersMe = (
  options?: SecondParameter<typeof customInstance>,
  signal?: AbortSignal,
) => {
  return customInstance<User>(
    { url: `/api/auth/me`, method: "GET", signal },
    options,
  );
};

export const getAuthReadUsersMeQueryKey = () => {
  return [`/api/auth/me`] as const;
};

export const getAuthReadUsersMeQueryOptions = <
  TData = Awaited<ReturnType<typeof authReadUsersMe>>,
  TError = ErrorType<void>,
>(options?: {
  query?: Partial<
    UseQueryOptions<Awaited<ReturnType<typeof authReadUsersMe>>, TError, TData>
  >;
  request?: SecondParameter<typeof customInstance>;
}) => {
  const { query: queryOptions, request: requestOptions } = options ?? {};

  const queryKey = queryOptions?.queryKey ?? getAuthReadUsersMeQueryKey();

  const queryFn: QueryFunction<Awaited<ReturnType<typeof authReadUsersMe>>> = ({
    signal,
  }) => authReadUsersMe(requestOptions, signal);

  return { queryKey, queryFn, ...queryOptions } as UseQueryOptions<
    Awaited<ReturnType<typeof authReadUsersMe>>,
    TError,
    TData
  > & { queryKey: DataTag<QueryKey, TData> };
};

export type AuthReadUsersMeQueryResult = NonNullable<
  Awaited<ReturnType<typeof authReadUsersMe>>
>;
export type AuthReadUsersMeQueryError = ErrorType<void>;

export function useAuthReadUsersMe<
  TData = Awaited<ReturnType<typeof authReadUsersMe>>,
  TError = ErrorType<void>,
>(
  options: {
    query: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof authReadUsersMe>>,
        TError,
        TData
      >
    > &
      Pick<
        DefinedInitialDataOptions<
          Awaited<ReturnType<typeof authReadUsersMe>>,
          TError,
          Awaited<ReturnType<typeof authReadUsersMe>>
        >,
        "initialData"
      >;
    request?: SecondParameter<typeof customInstance>;
  },
  queryClient?: QueryClient,
): DefinedUseQueryResult<TData, TError> & {
  queryKey: DataTag<QueryKey, TData>;
};
export function useAuthReadUsersMe<
  TData = Awaited<ReturnType<typeof authReadUsersMe>>,
  TError = ErrorType<void>,
>(
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof authReadUsersMe>>,
        TError,
        TData
      >
    > &
      Pick<
        UndefinedInitialDataOptions<
          Awaited<ReturnType<typeof authReadUsersMe>>,
          TError,
          Awaited<ReturnType<typeof authReadUsersMe>>
        >,
        "initialData"
      >;
    request?: SecondParameter<typeof customInstance>;
  },
  queryClient?: QueryClient,
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
export function useAuthReadUsersMe<
  TData = Awaited<ReturnType<typeof authReadUsersMe>>,
  TError = ErrorType<void>,
>(
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof authReadUsersMe>>,
        TError,
        TData
      >
    >;
    request?: SecondParameter<typeof customInstance>;
  },
  queryClient?: QueryClient,
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> };
/**
 * @summary Read Users Me
 */

export function useAuthReadUsersMe<
  TData = Awaited<ReturnType<typeof authReadUsersMe>>,
  TError = ErrorType<void>,
>(
  options?: {
    query?: Partial<
      UseQueryOptions<
        Awaited<ReturnType<typeof authReadUsersMe>>,
        TError,
        TData
      >
    >;
    request?: SecondParameter<typeof customInstance>;
  },
  queryClient?: QueryClient,
): UseQueryResult<TData, TError> & { queryKey: DataTag<QueryKey, TData> } {
  const queryOptions = getAuthReadUsersMeQueryOptions(options);

  const query = useQuery(queryOptions, queryClient) as UseQueryResult<
    TData,
    TError
  > & { queryKey: DataTag<QueryKey, TData> };

  query.queryKey = queryOptions.queryKey;

  return query;
}

/**
 * Logout endpoint.

This endpoint doesn't need to do anything on the backend since the token is managed client-side.
The client will remove the token from cookies.
 * @summary Logout
 */
export const authLogout = (
  options?: SecondParameter<typeof customInstance>,
  signal?: AbortSignal,
) => {
  return customInstance<unknown>(
    { url: `/api/auth/logout`, method: "POST", signal },
    options,
  );
};

export const getAuthLogoutMutationOptions = <
  TError = ErrorType<void>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof authLogout>>,
    TError,
    void,
    TContext
  >;
  request?: SecondParameter<typeof customInstance>;
}): UseMutationOptions<
  Awaited<ReturnType<typeof authLogout>>,
  TError,
  void,
  TContext
> => {
  const mutationKey = ["authLogout"];
  const { mutation: mutationOptions, request: requestOptions } = options
    ? options.mutation &&
      "mutationKey" in options.mutation &&
      options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, request: undefined };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof authLogout>>,
    void
  > = () => {
    return authLogout(requestOptions);
  };

  return { mutationFn, ...mutationOptions };
};

export type AuthLogoutMutationResult = NonNullable<
  Awaited<ReturnType<typeof authLogout>>
>;

export type AuthLogoutMutationError = ErrorType<void>;

/**
 * @summary Logout
 */
export const useAuthLogout = <TError = ErrorType<void>, TContext = unknown>(
  options?: {
    mutation?: UseMutationOptions<
      Awaited<ReturnType<typeof authLogout>>,
      TError,
      void,
      TContext
    >;
    request?: SecondParameter<typeof customInstance>;
  },
  queryClient?: QueryClient,
): UseMutationResult<
  Awaited<ReturnType<typeof authLogout>>,
  TError,
  void,
  TContext
> => {
  const mutationOptions = getAuthLogoutMutationOptions(options);

  return useMutation(mutationOptions, queryClient);
};
