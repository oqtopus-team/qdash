import type { QDashApiClient } from "./_generated/index.js";
import {
  buildApi,
  defaultSleep,
  sessionFetch,
  tokenProvider,
  type Context,
  type Fetch,
  type Sleep,
} from "./_http.js";
import { QDashConfig, type QDashConfigOptions } from "./config.js";
import { Dashboards, Scripts } from "./dashboards.js";
import { QDashConfigError } from "./errors.js";
import { Chip, Pipelines } from "./pipelines.js";
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

function checkedProject(projectId: unknown): string | undefined {
  if (projectId !== undefined && (typeof projectId !== "string" || !projectId)) {
    throw new QDashConfigError("projectId must be a non-empty string");
  }
  return projectId as string | undefined;
}

interface Shared {
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
  private readonly executions: Executions;
  private readonly [SHARED]: Shared;

  constructor(config: QDashConfig | QDashConfigOptions, options: QDashSessionOptions = {}) {
    const projectId = checkedProject(options.projectId);
    const base = config instanceof QDashConfig ? config : new QDashConfig(config);
    // A frozen copy: what the session reports is what its requests send.
    this.snapshot = projectId !== undefined ? base.with({ projectId }) : base.with({});
    const inherited = (options as { [SHARED]?: Shared })[SHARED];
    const fetchFn = inherited ? inherited.fetch : sessionFetch(this.snapshot, options.fetch);
    const env = inherited?.env ?? options.env ?? process.env;
    this[SHARED] = {
      fetch: fetchFn,
      env,
      sleep: inherited?.sleep ?? options.sleep ?? defaultSleep,
      token: inherited?.token ?? tokenProvider(this.snapshot, fetchFn, env),
    };
    this.api = buildApi(this.snapshot, {
      projectId: this.snapshot.projectId,
      fetch: fetchFn,
      token: this[SHARED].token,
    });
    const context: Context = {
      api: this.api,
      config: this.snapshot,
      reads: { attempts: this.snapshot.readAttempts, sleep: this[SHARED].sleep },
      sleep: this[SHARED].sleep,
      now: () => performance.now(),
    };
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
