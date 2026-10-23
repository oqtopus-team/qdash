/**
 * The agent-exec server: starts one pi-env daemon per runtime connection.
 *
 * Runs as PID 1 of the agent-exec container. Each connection from the Agent
 * Runtime's relay (src/exec-relay.ts) carries a hello line, then the daemon's
 * stdin; the daemon's stdout goes back the same way. With root the daemon runs
 * as the owner's own uid (`setpriv`) in a 0700 directory, so one user's shell
 * cannot read another user's files. The container holds no QDash credentials
 * and reaches no QDash service. A Unix socket writable only by the runtime's
 * group prevents workspace users from choosing another owner. See
 * docs/developer-guide/copilot/workspace.md.
 */
import { spawn, type ChildProcess } from "node:child_process";
import { chmodSync, chownSync, lstatSync, mkdirSync, readdirSync, unlinkSync } from "node:fs";
import { createServer, type Server, type Socket } from "node:net";
import { dirname, join } from "node:path";

import { DEFAULT_EXEC_SOCKET, HELLO_MAX_BYTES, ownerUid, parseHello, UID_BASE, UID_SPAN, workspaceName } from "./protocol.ts";

export interface ExecServerOptions {
  socketPath: string;
  /** Group allowed to connect; the runtime's bun user is gid 1000 in Compose. */
  socketGid?: number;
  /** Owner directories are created under this root. */
  workspaceRoot: string;
  /** The pi-env daemon binary. */
  daemon: string;
  /** Run each owner's daemon as its own uid through `setpriv`; needs root. */
  isolateUsers: boolean;
  log?: (message: string) => void;
}

export interface ExecServer {
  socketPath: string;
  close(): Promise<void>;
}

export async function startExecServer(options: ExecServerOptions): Promise<ExecServer> {
  const log = options.log ?? ((message: string) => console.log(`[agent-exec] ${message}`));
  mkdirSync(options.workspaceRoot, { recursive: true });
  if (options.isolateUsers) chmodSync(options.workspaceRoot, 0o755);
  const socketDir = dirname(options.socketPath);
  mkdirSync(socketDir, { recursive: true });
  chmodSync(socketDir, 0o750);
  if (options.socketGid !== undefined) chownSync(socketDir, process.getuid!(), options.socketGid);
  const stale = lstatSync(options.socketPath, { throwIfNoEntry: false });
  if (stale) {
    if (!stale.isSocket()) throw new Error("Refusing to replace a non-socket path");
    unlinkSync(options.socketPath);
  }
  const children = new Set<ChildProcess>();
  const sockets = new Set<Socket>();

  const start = (socket: Socket, owner: string, argv: readonly string[], rest: Buffer): void => {
    let uid: number | undefined;
    const name = workspaceName(owner);
    const ownerDir = join(options.workspaceRoot, name);
    try {
      uid = options.isolateUsers ? workspaceUid(options.workspaceRoot, owner) : undefined;
      prepareDir(ownerDir, uid);
    } catch (error) {
      log(`cannot prepare ${ownerDir}: ${error instanceof Error ? error.message : String(error)}`);
      socket.destroy();
      return;
    }
    const command =
      uid === undefined
        ? [options.daemon, ...argv]
        : ["setpriv", `--reuid=${uid}`, `--regid=${uid}`, "--clear-groups", "--", options.daemon, ...argv];
    const child = spawn(command[0]!, command.slice(1), {
      cwd: ownerDir,
      // Do not chown paths inside a user-owned directory: a user could replace
      // them with symlinks before the next connection.
      env: daemonEnv(ownerDir, ownerDir),
      stdio: ["pipe", "pipe", "pipe"],
    });
    children.add(child);
    log(`daemon for ${name} starting (pid ${child.pid ?? "?"}, uid ${uid ?? "server"})`);
    child.on("error", (error) => {
      log(`daemon for ${name} failed to start: ${error.message}`);
      children.delete(child);
      socket.destroy();
    });
    child.on("exit", (code, signal) => {
      children.delete(child);
      log(`daemon for ${name} exited (${signal ?? code})`);
      socket.end();
    });
    child.stdin.on("error", () => {});
    child.stderr.on("data", (chunk: Buffer) => log(`${name}: ${chunk.toString("utf8").trimEnd()}`));
    child.stdout.pipe(socket);
    if (rest.length > 0) child.stdin.write(rest);
    socket.pipe(child.stdin);
    socket.on("close", () => {
      // The daemon exits by itself when its stdin ends and kills what it started.
      if (child.exitCode === null && child.signalCode === null) child.kill("SIGTERM");
    });
  };

  const handle = (socket: Socket): void => {
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
    let buffered = Buffer.alloc(0);
    let started = false;
    socket.on("error", (error) => {
      if (!started) log(`connection error: ${error.message}`);
      socket.destroy();
    });
    socket.on("data", (chunk: Buffer) => {
      if (started) return;
      buffered = Buffer.concat([buffered, chunk]);
      const newline = buffered.indexOf(10);
      if (newline === -1) {
        if (buffered.length >= HELLO_MAX_BYTES) {
          log(`refused ${socket.remoteAddress ?? "?"}: hello too long`);
          socket.destroy();
        }
        return;
      }
      started = true;
      if (newline >= HELLO_MAX_BYTES) {
        socket.destroy();
        return;
      }
      const hello = parseHello(buffered.subarray(0, newline).toString("utf8"));
      if (!hello) {
        log(`refused ${socket.remoteAddress ?? "?"}: malformed hello`);
        socket.destroy();
        return;
      }
      start(socket, hello.owner, hello.argv, buffered.subarray(newline + 1));
      buffered = Buffer.alloc(0);
    });
  };

  const server: Server = createServer(handle);
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(options.socketPath, () => {
      chmodSync(options.socketPath, 0o660);
      if (options.socketGid !== undefined) chownSync(options.socketPath, process.getuid!(), options.socketGid);
      server.off("error", reject);
      resolve();
    });
  });
  return {
    socketPath: options.socketPath,
    close: () =>
      new Promise<void>((resolve) => {
        for (const child of children) child.kill("SIGTERM");
        // `server.close` waits for open connections; the daemons behind them are gone.
        for (const socket of sockets) socket.destroy();
        server.close(() => resolve());
      }),
  };
}

/** Owner directories sit under a root-owned parent, so their uids form the allocation registry. */
export function workspaceUid(root: string, owner: string): number {
  const name = workspaceName(owner);
  const used = new Set<number>();
  let existing: number | undefined;
  for (const entry of readdirSync(root)) {
    const stat = lstatSync(join(root, entry));
    if (!stat.isDirectory() || stat.uid < UID_BASE || stat.uid >= UID_BASE + UID_SPAN || used.has(stat.uid)) {
      throw new Error(`Invalid or duplicate workspace ownership: ${entry}`);
    }
    used.add(stat.uid);
    if (entry === name) existing = stat.uid;
  }
  return existing ?? ownerUid(owner, used);
}

function prepareDir(path: string, uid: number | undefined): void {
  mkdirSync(path, { recursive: true });
  if (uid !== undefined) {
    chownSync(path, uid, uid);
    chmodSync(path, 0o700);
  }
}

/** The daemon's environment, and so every command's: nothing from the server's own. */
function daemonEnv(home: string, tmpDir: string): Record<string, string> {
  return {
    PATH: "/usr/local/bin:/usr/bin:/bin",
    HOME: home,
    TMPDIR: tmpDir,
    LANG: "C.UTF-8",
    LC_ALL: "C.UTF-8",
    PYTHONDONTWRITEBYTECODE: "1",
    MPLCONFIGDIR: tmpDir,
  };
}

function flag(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined || value.trim() === "") return fallback;
  return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
}

if (import.meta.main) {
  const root = process.getuid?.() === 0;
  const isolateUsers = flag(process.env.AGENT_EXEC_ISOLATE_USERS, root);
  if (!isolateUsers) {
    console.warn("[agent-exec] running every owner's daemon as the server's own user (no per-user isolation)");
  }
  const server = await startExecServer({
    socketPath: process.env.AGENT_EXEC_SOCKET ?? DEFAULT_EXEC_SOCKET,
    socketGid: Number(process.env.AGENT_EXEC_SOCKET_GID ?? 1000),
    workspaceRoot: process.env.AGENT_EXEC_WORKSPACE_ROOT ?? "/workspace",
    daemon: process.env.AGENT_EXEC_DAEMON ?? "/usr/local/bin/pi-env",
    isolateUsers,
  });
  console.log(`[agent-exec] listening on ${server.socketPath}`);
  const stop = () => {
    void server.close().then(() => process.exit(0));
  };
  process.on("SIGTERM", stop);
  process.on("SIGINT", stop);
}
