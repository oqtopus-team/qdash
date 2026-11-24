import type { QDashConfig as ClientConfig } from "@oqtopus-team/qdash-client";
import { QDash, QDashResultUnknownError, type QDashSessionOptions } from "@oqtopus-team/qdash-sdk";

/**
 * The SDK session a tool runs on, for the client the tool already resolved from its profile or
 * the environment. The SDK is self-contained, so it gets the client's connection settings
 * rather than the client itself.
 */
export type SdkSessionFactory = (client: { config: ClientConfig }) => QDash;

/**
 * A factory of SDK sessions with the client's base URL, credentials, project, Cloudflare Access
 * headers, timeout, user agent and read attempts, and the given session options.
 *
 * The client's transport options (its `fetch`, default headers and environment) are private to
 * it and do not carry over: a host that built its client with a custom fetch passes the same
 * fetch here (`sdk: sdkSessionFactory({ fetch })` in a tool's dependencies). Proxy and TLS
 * overrides need such a fetch, as they do in the client. The client's retry backoff settings
 * do not apply; the SDK's own read backoff does.
 *
 * A session signs in on its first request when the profile uses a username and password, so a
 * tool call that also sends requests with the client signs in once for each.
 */
export function sdkSessionFactory(options: QDashSessionOptions = {}): SdkSessionFactory {
  return ({ config }) =>
    new QDash(
      {
        baseUrl: config.baseUrl,
        ...(config.apiToken ? { apiToken: config.apiToken } : {}),
        ...(config.username ? { username: config.username } : {}),
        ...(config.passwordEnv ? { passwordEnv: config.passwordEnv } : {}),
        ...(config.projectId ? { projectId: config.projectId } : {}),
        ...(config.cfAccessClientId ? { cfAccessClientId: config.cfAccessClientId } : {}),
        ...(config.cfAccessClientSecret ? { cfAccessClientSecret: config.cfAccessClientSecret } : {}),
        ...(config.proxy ? { proxy: config.proxy } : {}),
        timeoutSec: config.timeoutSeconds,
        verifyTls: config.verifyTls,
        userAgent: config.userAgent,
        // The client accepts any positive number and sends a read while the attempt number is
        // at most it; the SDK takes a whole number of attempts, at least one.
        readAttempts: Math.max(1, Math.floor(config.retry.maxAttempts)),
      },
      options,
    );
}

/** SDK sessions with the built-in fetch and `process.env`, as the pi-qdash tools use them. */
export const sdkSession: SdkSessionFactory = sdkSessionFactory();

/**
 * The SDK's error for a dispatch that may have started without its recording, also from
 * another copy of the SDK package.
 */
export function isResultUnknown(error: unknown): error is QDashResultUnknownError {
  return error instanceof QDashResultUnknownError || (error instanceof Error && error.name === "QDashResultUnknownError");
}

/**
 * The tool error for a launch whose outcome is unknown: never started again by the tool, and
 * named so the model checks the executions and tells the user instead of retrying.
 */
export function resultUnknownToolError(error: QDashResultUnknownError): Error {
  const executionId = typeof error.executionId === "string" && error.executionId ? error.executionId : undefined;
  return new Error(
    `${error.message} Do not start this run again; check qdash_list_executions` +
      `${executionId ? ` for execution ${executionId}` : ""} and tell the user.`,
    { cause: error },
  );
}
