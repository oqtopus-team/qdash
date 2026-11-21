import {
  QDashClient,
  QDashConfig,
  QDashConfigError,
  type QDashClientOptions,
} from "@oqtopus-team/qdash-client";

import { Dashboards, Scripts } from "./dashboards.js";
import { Chip, Pipelines } from "./pipelines.js";
import { Workflows } from "./workflows.js";

export interface QDashSessionOptions {
  /**
   * Send this project as `X-Project-Id` on every request of the session. The
   * given client and its configuration are not changed. Without it the session
   * uses the client's configured project, or none, in which case the server
   * applies the user's default project.
   */
  projectId?: string;
}

export interface QDashFactoryOptions extends QDashSessionOptions {
  /** Options of the `QDashClient` the session creates, such as a custom `fetch`. */
  clientOptions?: QDashClientOptions;
}

function checkedProject(projectId: string | undefined): string | undefined {
  if (projectId !== undefined && (typeof projectId !== "string" || !projectId)) {
    throw new QDashConfigError("projectId must be a non-empty string");
  }
  return projectId;
}

/**
 * Entry point of the QDash SDK: one configured `QDashClient` and the domain
 * operations on it. Creating a session, a chip or a workflow handle sends no
 * request, and the session holds nothing to close.
 */
export class QDash {
  /** The underlying client, for routes the SDK does not wrap. */
  readonly client: QDashClient;
  readonly pipelines: Pipelines;
  readonly workflows: Workflows;
  readonly scripts: Scripts;
  readonly dashboards: Dashboards;

  constructor(client: QDashClient, options: QDashSessionOptions = {}) {
    const projectId = checkedProject(options.projectId);
    this.client = projectId !== undefined ? client.withProject(projectId) : client;
    this.pipelines = new Pipelines(this.client);
    this.workflows = new Workflows(this.client);
    this.scripts = new Scripts(this.client);
    this.dashboards = new Dashboards(this.client);
  }

  /** A session configured from `QDASH_*` environment variables. */
  static fromEnv(
    options: QDashFactoryOptions & { env?: Record<string, string | undefined> } = {},
  ): QDash {
    const env = options.env ?? process.env;
    return QDash.owning(QDashConfig.fromEnv(env), options, env);
  }

  /** A session configured from a profile of the client's config file. */
  static async fromProfile(
    profile = "default",
    path?: string,
    options: QDashFactoryOptions = {},
  ): Promise<QDash> {
    const config = path
      ? await QDashConfig.fromFile(profile, path)
      : await QDashConfig.fromFile(profile);
    return QDash.owning(config, options);
  }

  private static owning(
    config: QDashConfig,
    options: QDashFactoryOptions,
    env?: Record<string, string | undefined>,
  ): QDash {
    const projectId = checkedProject(options.projectId);
    const scoped = projectId !== undefined ? new QDashConfig({ ...config, projectId }) : config;
    const clientOptions = env ? { ...options.clientOptions, env } : (options.clientOptions ?? {});
    return new QDash(new QDashClient(scoped, clientOptions));
  }

  /** The project sent as `X-Project-Id`, or undefined for the server's default. */
  get projectId(): string | undefined {
    return this.client.config.projectId;
  }

  /** Calibration on `chipId` through this session; sends no request. */
  chip(chipId: string): Chip {
    return new Chip(this.pipelines, chipId);
  }
}
