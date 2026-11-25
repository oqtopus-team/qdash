import type { QDashApiClient } from "./_generated/index.js";
import {
  buildApi,
  call,
  defaultSleep,
  passthrough,
  read,
  sessionAuth,
  sessionFetch,
  writeOptions,
  type CallOptions,
  type Context,
  type Fetch,
  type FetchOptions,
  type Sleep,
} from "./_http.js";
import { QDashConfig, type QDashConfigOptions } from "./config.js";
import { Dashboards, Scripts } from "./dashboards.js";
import { QDashConfigError } from "./errors.js";
import { Chip, Pipelines, preflightCalibrationSession } from "./pipelines.js";
import { TaskResults } from "./results.js";
import { Executions, Run } from "./runs.js";
import { Workflows } from "./workflows.js";

type Environment = Readonly<Record<string, string | undefined>>;

export interface QDashSessionOptions {
  /**
   * Send this project as `X-Project-Id` on every request of the session, instead of the
   * config's `projectId`. The given config is not changed. Without either, the server applies
   * the user's default project.
   */
  projectId?: string;
  /**
   * The fetch every request goes through, such as one that applies a proxy, custom TLS or test
   * responses. Required when the config sets `proxy` or `verifyTls: false`.
   */
  fetch?: Fetch;
  /** Where `passwordEnv` is looked up for a username/password sign-in (default `process.env`). */
  env?: Environment;
  /** Waits between polls and read retries; for tests (default a timer). */
  sleep?: Sleep;
}

/** Options of `QDash.fromEnv` and `QDash.fromProfile`. */
export type QDashFactoryOptions = QDashSessionOptions;

/**
 * Request options `QDash.read` and `QDash.send` give a generated call: retries off (the SDK
 * applies its own) and the caller's abort signal. Pass them on as the call's request options.
 */
export type QDashCallOptions = CallOptions;

/** Options of `QDash.read`, `QDash.send` and `QDash.preflightCalibrationSession`. */
export interface QDashRequestOptions {
  /** Cancels the request and its retries; the call rejects with the signal's reason. */
  signal?: AbortSignal;
}

export type { FetchOptions as QDashFetchOptions, QueryValue as QDashQueryValue } from "./_http.js";

function checkedProject(projectId: unknown): string | undefined {
  if (projectId !== undefined && (typeof projectId !== "string" || !projectId)) {
    throw new QDashConfigError("projectId must be a non-empty string");
  }
  return projectId as string | undefined;
}

interface Shared {
  /** The fetch of API requests, which drops a sign-in after a 401 (see `sessionAuth`). */
  fetch: Fetch | undefined;
  env: Environment;
  sleep: Sleep;
  token: string | (() => Promise<string>);
}

const SHARED = Symbol("qdash.shared");

/**
 * Entry point of the QDash SDK: one configuration, the generated client of the whole API on it
 * (`api`) and the domain helpers. Creating a session, a chip or a workflow handle sends no
 * request, and the session holds nothing to close.
 *
 * The session keeps its own frozen copy of the configuration: `config` and `projectId` report
 * exactly what its requests send, and changing the options it was built from changes nothing.
 * `withProject` returns a session for another project; this one is unchanged.
 *
 * The helpers (`pipelines`, `workflows`, `scripts`, `dashboards`, `taskResults`, `chip`,
 * `run`) throw the SDK's errors, send every write once and send reads again after a transient
 * failure, up to `config.readAttempts` in total. `api` sends every call once unless the call
 * asks for retries with `{ maxRetries }`, and throws the generated `ApiError` types.
 *
 * A username/password sign-in happens on the first request and is shared with `withProject`
 * sessions. A 401 answer, to a helper or an `api` call, drops that sign-in so the next request
 * signs in again; the request that got the 401 is not sent again and throws it.
 */
export class QDash {
  /**
   * The generated client of the whole API, with this session's auth and project. Resources
   * follow the API's tags, e.g. `qdash.api.chip.listChips()` or
   * `qdash.api.execution.getExecution({ execution_id })`; requests and responses use the API's
   * snake_case keys.
   */
  readonly api: QDashApiClient;
  readonly pipelines: Pipelines;
  readonly workflows: Workflows;
  readonly scripts: Scripts;
  readonly dashboards: Dashboards;
  /** Compound task-result reads, such as `compareLatest` and `evidence`. */
  readonly taskResults: TaskResults;

  private readonly snapshot: QDashConfig;
  private readonly context: Context;
  private readonly executions: Executions;
  private readonly [SHARED]: Shared;

  constructor(config: QDashConfig | QDashConfigOptions, options: QDashSessionOptions = {}) {
    const projectId = checkedProject(options.projectId);
    const base = config instanceof QDashConfig ? config : new QDashConfig(config);
    // A frozen copy: what the session reports is what its requests send.
    this.snapshot = projectId !== undefined ? base.with({ projectId }) : base.with({});
    const inherited = (options as { [SHARED]?: Shared })[SHARED];
    if (inherited) {
      this[SHARED] = inherited;
    } else {
      const env = options.env ?? process.env;
      const auth = sessionAuth(this.snapshot, sessionFetch(this.snapshot, options.fetch), env);
      this[SHARED] = { fetch: auth.fetch, env, sleep: options.sleep ?? defaultSleep, token: auth.token };
    }
    this.api = buildApi(this.snapshot, {
      projectId: this.snapshot.projectId,
      fetch: this[SHARED].fetch,
      token: this[SHARED].token,
    });
    const context: Context = {
      api: this.api,
      config: this.snapshot,
      reads: { attempts: this.snapshot.readAttempts, sleep: this[SHARED].sleep },
      sleep: this[SHARED].sleep,
      now: () => performance.now(),
    };
    this.context = context;
    this.executions = new Executions(context);
    this.pipelines = new Pipelines(context, this.executions);
    this.workflows = new Workflows(context, this.executions);
    this.scripts = new Scripts(context);
    this.dashboards = new Dashboards(context);
    this.taskResults = new TaskResults(context);
  }

  /** A session configured from `QDASH_*` environment variables (`options.env`, else `process.env`). */
  static fromEnv(options: QDashFactoryOptions = {}): QDash {
    return new QDash(QDashConfig.fromEnv(options.env ?? process.env), options);
  }

  /**
   * A session configured from a profile of the QDash config file. The file and profile
   * resolve as in `QDashConfig.fromFile`: `config.toml` and its `default_profile` unless
   * `path` or `profile` is given.
   */
  static async fromProfile(profile?: string, path?: string, options: QDashFactoryOptions = {}): Promise<QDash> {
    const config = await QDashConfig.fromFile(profile, path, options.env ? { env: options.env } : {});
    return new QDash(config, options);
  }

  /**
   * A session scoped to `projectId`, with this session's fetch, environment and sign-in. This
   * session and its configuration are unchanged.
   */
  withProject(projectId: string): QDash {
    const checked = checkedProject(projectId);
    if (checked === undefined) throw new QDashConfigError("projectId must be a non-empty string");
    return new QDash(this.snapshot, { projectId: checked, [SHARED]: this[SHARED] } as QDashSessionOptions);
  }

  /** The session's settings, frozen; use `withProject()` to change the project. */
  get config(): QDashConfig {
    return this.snapshot;
  }

  /** The project sent as `X-Project-Id`, or undefined for the server's default. */
  get projectId(): string | undefined {
    return this.snapshot.projectId;
  }

  /**
   * Send a read of the generated client with the helpers' read policy: sent again after a
   * transport error or a status of 408, 429, 500, 502, 503 or 504, up to `config.readAttempts`
   * in total, and failing with the SDK's errors (`QDashNotFoundError` for 404 and so on). Pass
   * the given options to the call, e.g.
   * `qdash.read((o) => qdash.api.chip.listChips(o))`. Use it only for requests that change
   * nothing: a request is sent again without checking its method.
   */
  read<T>(request: (options: QDashCallOptions) => Promise<T>, options: QDashRequestOptions = {}): Promise<T> {
    return read({ ...this.context.reads, ...(options.signal ? { signal: options.signal } : {}) }, request);
  }

  /**
   * Send a call of the generated client once, failing with the SDK's errors; for requests that
   * change state. Pass the given options to the call, e.g.
   * `qdash.send((o) => qdash.api.forum.createForumPost(body, o))`.
   */
  send<T>(request: (options: QDashCallOptions) => Promise<T>, options: QDashRequestOptions = {}): Promise<T> {
    return call(() => request(writeOptions(options.signal)), options.signal);
  }

  /**
   * Send a request to `path` of the API, such as `/executions/figure`, with this session's
   * auth, project, headers, timeout and fetch, for a route the generated client has no
   * usable method for: a binary or text download, or any GET by path. Resolves with the
   * response of a success status, its body unread; an error status throws the SDK's error for
   * it. GET and HEAD follow the read policy of `read`; other methods are sent once. `path` is
   * relative to the API root; an absolute URL is refused, so credentials never leave it.
   */
  fetch(path: string, options: FetchOptions = {}): Promise<Response> {
    return passthrough(this.context, this.snapshot.projectId, path, options);
  }

  /**
   * Check that `calibrationSessionId` is a calibration session of the signed-in user on
   * `chipId` before a write that records into it, such as creating an agent session in it:
   * reads the session list, never the detail, so an automatic session is not closed. Throws
   * `QDashPreflightError` when the session is not found, or the server cannot list sessions,
   * so the caller sends nothing.
   */
  preflightCalibrationSession(calibrationSessionId: string, chipId: string, options: QDashRequestOptions = {}): Promise<void> {
    return preflightCalibrationSession(this.context, calibrationSessionId, chipId, options.signal);
  }

  /** Calibration on `chipId` through this session; sends no request. */
  chip(chipId: string): Chip {
    return new Chip(this.pipelines, chipId);
  }

  /** A handle to follow an execution already dispatched; sends no request. */
  run(executionId: string): Run {
    if (typeof executionId !== "string" || !executionId) throw new TypeError("executionId must be a non-empty string");
    return new Run(this.executions, executionId);
  }
}
