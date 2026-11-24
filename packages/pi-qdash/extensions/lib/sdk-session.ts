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

/** Where a launch whose outcome is unknown was meant to run, for finding it without an ID. */
export interface LaunchTarget {
  /** The chip the launch was for, when the tool knows it. */
  chipId?: string;
  /** How to name the chip when `chipId` is unknown, such as "the flow's saved chip". */
  chipHint?: string;
}

/**
 * What the model does after a launch whose outcome is unknown: never start it again, check the
 * run and tell the user. With an execution ID it points at `qdash_get_execution`, which finds
 * the run on any chip; without one, at `qdash_list_executions` for the launch's chip, page by
 * page, since that tool reads one chip (the default one unless told otherwise) a page at a time.
 */
export function unknownLaunchGuidance(executionId: string | undefined, target: LaunchTarget = {}): string {
  const chip = target.chipId ? `chipId ${target.chipId}` : `chipId set to ${target.chipHint ?? "the launch's chip"}`;
  const check = executionId
    ? `check execution ${executionId} with qdash_get_execution`
    : `no execution ID was returned, so look for the run with qdash_list_executions, passing ${chip}, ` +
      "and page with skip until the rows are older than this launch";
  return `Do not start this run again; ${check}, and tell the user.`;
}

/** The tool error for a launch whose outcome is unknown (see `unknownLaunchGuidance`). */
export function resultUnknownToolError(error: QDashResultUnknownError, target: LaunchTarget = {}): Error {
  const executionId = typeof error.executionId === "string" && error.executionId ? error.executionId : undefined;
  return new Error(`${error.message} ${unknownLaunchGuidance(executionId, target)}`, { cause: error });
}
