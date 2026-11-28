import { QDash, QDashResultUnknownError, type QDashSessionOptions } from "@oqtopus-team/qdash-sdk";

/**
 * The SDK session a tool runs its SDK helpers (pipelines, workflows, scripts, task-result
 * evidence) on, for the connection the tool resolved from its profile or the environment.
 */
export type SdkSessionFactory = (client: { qdash: QDash }) => QDash;

/**
 * A factory of SDK sessions with the connection's settings (base URL, credentials, project,
 * Cloudflare Access headers, timeout, user agent and read attempts) and the given session
 * options, such as a test's fetch. A session it returns signs in on its own.
 */
export function sdkSessionFactory(options: QDashSessionOptions = {}): SdkSessionFactory {
  return ({ qdash }) => new QDash(qdash.config, options);
}

/** The connection's own SDK session: the same fetch, sign-in and project as its other requests. */
export const sdkSession: SdkSessionFactory = ({ qdash }) => qdash;

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
