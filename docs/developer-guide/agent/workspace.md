# Agent Workspace

Chat shell and file tools run in `agent-exec`, a separate container with no QDash credentials or
network. The Agent Runtime never executes model-written shell commands locally.

## Request flow

The runtime opens an `ExecWorkspace` for a conversation and connects over a shared Unix socket.
The first tool call creates the directory and starts a pi-env daemon under the owner's uid.
Closing the connection stops that daemon's processes.

Branches share their source chat's directory and see its current files. Deleting the last chat
using a store removes its workspace. Chats that never use tools create no workspace.

## Isolation

| Boundary | Enforcement |
| --- | --- |
| Credentials | Scrubbed daemon environment; no QDash token or model key |
| Network | `network_mode: none` |
| Users | Distinct owner uids and mode 0700 directories |
| Container | Read-only root, bounded resources, restricted capabilities |
| Runtime socket | Accessible to the runtime group, not workspace users |

Conversations of the same owner can access each other's files. This is owner isolation, not
conversation isolation. Conflicting persisted uid ownership is refused rather than shared.

## Configuration

| Variable | Default / purpose |
| --- | --- |
| `AGENT_EXEC_SOCKET` | Compose: `/run/agent-exec/exec.sock`; unset disables tools |
| `AGENT_EXEC_SOCKET_GID` | `1000`, the runtime group |
| `AGENT_EXEC_WORKSPACE_ROOT` | `/workspace` |
| `AGENT_EXEC_ISOLATE_USERS` | On when the server runs as root |
| `AGENT_EXEC_MEMORY_LIMIT` | `2g` |
| `AGENT_EXEC_CPU_LIMIT` | `2` |

Without a socket the model gets no shell/file tools. Workspace plots reach chat through
`render_chart`; writing a file does not itself display it.

## Change and test

Run `task ci-agent-runtime`. The exec protocol/server tests exercise real Unix-socket commands,
file operations, cleanup, and malformed requests. User-isolation tests require root.

Add Python packages to `agent-runtime/exec/requirements.txt` and rebuild `agent-exec`.
Keep arbitrary execution out of the runtime and never add QDash credentials to the exec image.

## Implementation files

| File | Responsibility |
| --- | --- |
| `agent-runtime/src/exec-env.ts` | Workspace lifecycle |
| `agent-runtime/src/exec-relay.ts` | Socket relay |
| `agent-runtime/exec/protocol.ts` | Connection validation |
| `agent-runtime/exec/server.ts` | Owner identity and daemon supervision |
| `compose.yaml` | Container isolation and volumes |
