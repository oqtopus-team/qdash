/**
 * The Copilot workspace: a conversation's directory and shell in the
 * agent-exec container, offered to the model as pi-durable's `read`,
 * `write`, `edit` and `bash` tools.
 *
 * The runtime itself never runs model-written code. Each open conversation
 * holds one pi-env `Connection`, whose daemon the agent-exec server starts
 * for the conversation's owner (exec/server.ts) through the Unix socket relay
 * (exec-relay.ts); pi-env's `RemoteExecutionEnv` then performs every file
 * operation and command there. Nothing is configured when AGENT_EXEC_SOCKET
 * is unset: the tools are not offered and the runtime works as before.
 */
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import type { ExecutionEnv } from "@earendil-works/pi-durable/env";
import { Connection, RemoteExecutionEnv } from "@earendil-works/pi-env";

import { workspaceName } from "../exec/protocol.ts";

/** The pi-durable coding tools the workspace enables, as the model sees them. */
export const WORKSPACE_TOOL_NAMES = ["bash", "edit", "read", "write"] as const;

/** `FileSystem.id`: every conversation's environment sees the same container. */
export const WORKSPACE_ENV_ID = "agent-exec";

export interface ExecConfig {
  socketPath: string;
  /** Where the server keeps owner directories; the same path on both sides. */
  workspaceRoot: string;
}

/** The workspace configuration from the environment, or `undefined` when none is set. */
export function execConfigFromEnv(env: NodeJS.ProcessEnv = process.env): ExecConfig | undefined {
  const socketPath = env.AGENT_EXEC_SOCKET?.trim();
  if (!socketPath) return undefined;
  return { socketPath, workspaceRoot: env.AGENT_EXEC_WORKSPACE_ROOT?.trim() || "/workspace" };
}

/** A conversation's directory: under its owner's, named like the server names them. */
export function workspacePath(root: string, ownerId: string, sessionId: string): string {
  return join(root, workspaceName(ownerId), workspaceName(sessionId));
}

const RELAY = join(dirname(fileURLToPath(import.meta.url)), "exec-relay.ts");

type Log = (message: string) => void;
const defaultLog: Log = (message) => console.log(`[agent-runtime] ${message}`);

function openConnection(config: ExecConfig, ownerId: string, log: Log): Connection {
  return new Connection({
    command: [process.execPath, RELAY, "--socket", config.socketPath, "--owner", ownerId],
    onLog: (text) => log(`agent-exec: ${text.trimEnd()}`),
  });
}

/** One conversation's workspace; `close()` stops its daemon and every command it runs. */
export class ExecWorkspace {
  readonly cwd: string;
  private readonly connection: Connection;
  private prepared: Promise<void> | undefined;

  constructor(
    private readonly config: ExecConfig,
    ownerId: string,
    sessionId: string,
    private readonly log: Log = defaultLog,
  ) {
    this.cwd = workspacePath(config.workspaceRoot, ownerId, sessionId);
    this.connection = openConnection(config, ownerId, log);
  }

  /** The environment of one tool call; the directory is created on first use. */
  async env(cwd: string = this.cwd): Promise<ExecutionEnv> {
    this.prepared ??= this.prepare();
    try {
      await this.prepared;
    } catch (error) {
      this.prepared = undefined;
      throw error;
    }
    return this.envAt(cwd);
  }

  close(): void {
    this.connection.close();
  }

  private envAt(cwd: string): RemoteExecutionEnv {
    return new RemoteExecutionEnv({ connection: this.connection, id: WORKSPACE_ENV_ID, cwd });
  }

  private async prepare(): Promise<void> {
    const result = await this.envAt(dirname(this.cwd)).createDir(this.cwd, { recursive: true }, BACKGROUND_CONTEXT);
    if (!result.ok) throw result.error;
    this.log(`workspace ${this.cwd} ready`);
  }
}

/** Delete a conversation's directory, as its owner; nothing to do when it never existed. */
export async function removeWorkspace(
  config: ExecConfig,
  ownerId: string,
  sessionId: string,
  log: Log = defaultLog,
): Promise<void> {
  const connection = openConnection(config, ownerId, log);
  try {
    const ownerDir = join(config.workspaceRoot, workspaceName(ownerId));
    const env = new RemoteExecutionEnv({ connection, id: WORKSPACE_ENV_ID, cwd: ownerDir });
    const result = await env.remove(
      workspacePath(config.workspaceRoot, ownerId, sessionId),
      { recursive: true, force: true },
      BACKGROUND_CONTEXT,
    );
    if (!result.ok) throw result.error;
  } finally {
    connection.close();
  }
}
