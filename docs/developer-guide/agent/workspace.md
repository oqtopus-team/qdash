# Agent Workspace

The workspace is the shell and file system behind the chat's `bash`, `read`, `write`, and
`edit` tools: a directory per conversation in the `agent-exec` container, which holds no
QDash credentials and reaches no QDash service. The Agent Runtime never runs model-written
code itself.

## Responsibility boundary

| Part | Owns | Leaves to others |
| --- | --- | --- |
| `agent-exec` container (`agent-runtime/exec/`) | Running commands and file operations, one pi-env daemon per conversation as the owner's own uid | Authentication, QDash data, model access, [metric scripts](../architecture/metric-scripts.md) (the `metric-runner` container) |
| Agent Runtime (`agent-runtime/src/exec-env.ts`) | One connection per open conversation, the conversation's directory, the four tools | Executing anything locally |

The model gets data into the workspace by writing it into a file. The container uses
`network_mode: none`; the runtime connects through a shared Unix socket.

## Request flow

```mermaid
sequenceDiagram
    participant H as Harness (pi-durable)
    participant W as ExecWorkspace
    participant R as exec-relay.ts
    participant S as exec/server.ts
    participant D as pi-env daemon
    H->>W: env({ cwd }) for a tool call
    W->>R: Connection starts the relay (first call only)
    R->>S: Unix socket: hello line {owner, argv}
    S->>D: setpriv --reuid=<owner uid> pi-env serve --token <hex>
    D-->>R: PI-ENV <hex>, then frames
    H->>D: exec / readTextFile / writeFile ... through RemoteExecutionEnv
```

1. `SharedRuntime.openSession` creates an `ExecWorkspace` for the owner and the chat's store
   session (the chat's own session ID, or for a branch the store it shares; see
   [Branches](./chat-streaming.md#branches)) and
   passes `env: (target) => workspace.env(target.cwd)` to `Harness.open`, with the agent's
   `cwd` set to the conversation's directory.
2. The first tool call creates that directory (`createDir`, recursive) and starts the
   connection. pi-env's `Connection` spawns `bun src/exec-relay.ts --socket ... --owner <id>`
   and appends `serve --token <hex>`; the relay sends the hello line and then pipes the
   daemon's stdin and stdout over the Unix socket, interpreting nothing.
3. `exec/server.ts` checks the hello's shape (`parseHello`), creates
   `/workspace/<owner>/` as the owner's uid with mode 0700, and starts the daemon there.
   Without root (tests, `AGENT_EXEC_ISOLATE_USERS=false`) it runs the daemon as itself.
4. pi-durable's tools call `RemoteExecutionEnv`, so results match `NodeExecutionEnv` on the
   container.
5. Closing the conversation closes the connection; the daemon then kills every process it
   started. The first tool call also writes a marker file beside the session's SQLite store
   (`<store>.workspace`); deleting the last QDash chat session that uses the store removes the
   directory only when that marker exists (`deleteSessionState` → `removeWorkspace`), so a chat
   or evaluation that never ran code starts no daemon and creates no owner directory. A chat and
   its branches share one directory: a branch sees the files as they are now, not as they were at
   the answer it was branched from.

## Isolation

| Boundary | Enforcement |
| --- | --- |
| Credentials | No `env_file`; the daemon's environment is `PATH`, `HOME`, `TMPDIR`, locale, and Python settings (`daemonEnv` in `exec/server.ts`) |
| Network | `network_mode: none`; no TCP listener |
| Users | A distinct uid in 20000–59999 per owner, persisted as directory ownership; 0700 owner directories |
| Container | `read_only` root with `/tmp` as tmpfs, `cap_drop: ALL` plus the capabilities `setpriv` and `chown` need, `no-new-privileges`, a pid limit (512), a memory limit (`AGENT_EXEC_MEMORY_LIMIT`, default 2g), a CPU limit (`AGENT_EXEC_CPU_LIMIT`, default 2) |
| Runtime access | A root-owned Unix socket (0660) in a root-owned directory (0750), both assigned to the runtime's group (gid 1000 in Compose); workspace users have no access |

The `agent-exec-socket` volume exposes the socket to the runtime as a read-only mount.
No shared authentication token is required. `workspaceUid` reuses an owner's directory uid
or chooses an unused uid when the name's hash collides. Entries under the root that are not
owner directories (a stray file, a directory owned outside the uid range) are ignored. An
owner whose directory shares its uid with another directory is refused rather than given a
shared identity; an operator must correct that ownership before that owner's workspace works.

Two conversations of the same owner can read each other's files through `bash`; a different
owner's directory is unreadable. A command runs as long as the model's `timeout` allows, and
the conversation's stop button aborts it with the turn.

## What the model sees

With `AGENT_EXEC_SOCKET` set, the system prompt describes the workspace (Python 3 with numpy,
scipy, pandas, plotly and matplotlib; no network; no QDash access) and the tool list in
**Settings → Agent** shows `bash`, `edit`, `read`, and `write`. Without it, the prompt says
there is no filesystem or shell, and the tools are not offered. A Plotly figure still reaches
the chat only through `render_chart`.

## In the chat

Workspace tool rows start collapsed, with a tool icon and a short activity label such as
**Running bun** or **Writing fit.py**. Opening a row shows the command for `bash`, the file and
its code for `write`, the old and new text of each `edit`, or the file for `read`. The expanded
row also shows the tool's answer (`output` on `tool_end`, the tail when long, with the exit code
of a failed command). The user's open or closed choice persists as the call starts and finishes.
While the model writes a call, an expanded row shows the code as it is typed (`tool_draft` and
`tool_args_delta` in [Chat Streaming](./chat-streaming.md)). A save of a flow
(`qdash_save_flow`) or a metric script (`qdash_save_metric_script`) shows the whole source as
code on its approval card. Components:
`ui/src/components/features/chat/ToolStepDetails.tsx`, `ChatInteractionCards.tsx`.

## Configuration

| Variable | Service | Meaning |
| --- | --- | --- |
| `AGENT_EXEC_SOCKET` | both | Unix socket path, `/run/agent-exec/exec.sock` in Compose; unset on the runtime to disable workspace tools |
| `AGENT_EXEC_SOCKET_GID` | agent-exec | Group allowed to connect, default `1000` (the runtime's `bun` group) |
| `AGENT_EXEC_WORKSPACE_ROOT` | both | Owner directories, default `/workspace` (the `agent-exec-workspace` volume) |
| `AGENT_EXEC_ISOLATE_USERS` | agent-exec | Per-owner uids; default on when the server runs as root |
| `AGENT_EXEC_MEMORY_LIMIT` | agent-exec | Container memory limit, default `2g` |
| `AGENT_EXEC_CPU_LIMIT` | agent-exec | Container CPU limit, default `2` |

The Python packages are pinned in `agent-runtime/exec/requirements.txt`; the daemon binary
comes from the `@earendil-works/pi-env` package the runtime depends on, so its version follows
`agent-runtime/package.json`.

## Change and test

Tests live in `agent-runtime/test/exec-protocol.test.mjs` (hello validation, names, uids,
configuration) and `exec-server.test.mjs`, which starts the real server and daemon on a
Unix socket and runs commands, file operations, and a second conversation through the
relay, and checks that a malformed hello closes the connection. A root-only test verifies
that colliding owners cannot read each other's files or connect to the socket; it skips
when the test runner cannot change uid. Run `task ci-agent-runtime`. The image uses the
repository root as its build context (`docker compose build agent-exec`).

To add a Python package, extend `requirements.txt` and rebuild `agent-exec`. To offer the
model no workspace, leave `AGENT_EXEC_SOCKET` unset on `agent-runtime`.

## Implementation files

- `agent-runtime/exec/protocol.ts`: hello parsing, `workspaceName`, `ownerUid`
- `agent-runtime/exec/server.ts`: the Unix socket server, uid allocation, and daemon supervisor
- `agent-runtime/exec/Dockerfile`, `agent-runtime/exec/requirements.txt`: the image
- `agent-runtime/src/exec-relay.ts`: the stdin/stdout to Unix socket relay
- `agent-runtime/src/exec-env.ts`: `ExecWorkspace`, `removeWorkspace`, `execConfigFromEnv`
- `agent-runtime/src/runtime.ts`: `openSession` and `deleteSessionState` wiring
- `compose.yaml`: the `agent-exec` service, `agent-exec-socket`, and `agent-exec-workspace` volumes
