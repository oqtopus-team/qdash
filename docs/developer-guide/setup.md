# Developer Setup

QDash development starts from a local repository checkout and uses either DevContainer or Nix for
the project toolchain.

## Prerequisites

### Required Tools

| Tool | Version | Description |
| --- | --- | --- |
| [Docker](https://docs.docker.com/get-docker/) | - | Container virtualization platform |
| [Docker Compose](https://docs.docker.com/compose/install/) | v2.24.4+ | Management of multiple Docker containers |
| [go-task](https://taskfile.dev/installation/) | v3.41+ | Task runner for development commands |
| [uv](https://docs.astral.sh/uv/) | - | Python package manager |

### Optional Tools (for local development)

| Tool | Version | Description |
| --- | --- | --- |
| [Python](https://www.python.org/downloads/) | 3.11-3.12 | Backend development |
| [Bun](https://bun.sh/) | 1.4.0+ | Frontend package manager and runtime |
| [Node.js](https://nodejs.org/) | 24.22.1+ (24.x) or 26.12.1+ | Next.js production runtime |

## Clone the Repository

Clone QDash on the development host. Keep the checkout in a directory where you want to store
other repositories too:

```bash
git clone https://github.com/oqtopus-team/qdash.git
cd qdash
```

The DevContainer mounts this checkout at `/workspace/qdash` and its host parent at
`/workspace/repos`. Changes are visible in both environments; additional repositories cloned
under `/workspace/repos` appear beside QDash on the host. Use `/workspace/qdash` for QDash
development so dependencies stay in its separate volumes.

To share another directory, create it on the host and export its absolute path as
`QDASH_SHARED_REPOS_DIR` before starting the container. It must be writable by your host user.
Setting it only in `.env` does not reach the host-side preflight check.

A DevContainer can start without `.env`. Before running Qubex-backed calibration tasks, follow
[Operator Setup](../user-guide/setup.md) for `.env` and `CONFIG_PATH` configuration.

## DevContainer

The recommended way to develop is using the DevContainer:

```shell
.devcontainer/check-shared-repos.sh "$PWD" && docker compose -f compose.devcontainer.yaml up -d
```

The check also runs automatically when opening the DevContainer through VS Code. It prevents a
missing shared directory from being created by Compose versions that ignore
`create_host_path: false`.

The DevContainer can start without a local `.env`; Docker Compose uses `.env` when present. The
checked-in VS Code configuration runs its remote session as the `vscode` user so files created in
the checkout remain writable from the host. Docker Compose direct sessions can still use `root`
when needed.

On Linux, build the `vscode` user with the host UID and GID so files created in the checkout
and shared repository directory remain writable from both the host and the container. VS Code's
`updateRemoteUserUID` handles this for Dev Containers opened through the extension; when
starting Compose directly, pass the IDs explicitly:

```shell
.devcontainer/check-shared-repos.sh "$PWD" && \
  LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose -f compose.devcontainer.yaml up -d --build
```

The container mounts `/var/run/docker.sock` so devcontainer users can run the local Docker
Compose tasks from inside the workspace. The Docker daemon resolves bind mounts on the host,
so on start the container links the checkout's host path (`QDASH_HOST_WORKSPACE`, set by VS
Code from `${localWorkspaceFolder}` or by `compose.devcontainer.yaml` from `$PWD`) to
`/workspace/qdash`; run `docker compose` from that host path inside the container, never from
`/workspace/qdash` directly. In the default VS Code session, tools under
`/home/vscode/.local` and agent configuration under `/home/vscode/.claude` and
`/home/vscode/.codex` are persisted in Docker volumes, so they survive container rebuilds.
Codex itself is installed under `/opt/codex`, which remains writable by the `vscode` user for
CLI updates without being hidden by the persisted `.local` volume. Host-side deployment commands
keep their Python environment outside the checkout, so they do not reuse root-owned DevContainer
artifacts.

Use the same `task` commands from the host or DevContainer. Both sessions edit the same source
checkout and use the same Docker daemon. Run Git and development commands as the `vscode` user
in the DevContainer; reserve root for container setup. The container sets `umask 022` so new
files are readable in both environments. Git credentials and global identity are per-user; set
`user.name` and `user.email` in both environments, and authenticate Git separately in each
environment. A repository-local Git setting is shared because `.git/config` is in the bind mount.

The DevContainer keeps its Python `.venv` in a Docker volume mounted at the usual workspace path.
The host retains its own `.venv`, so running `uv sync` or `uv run` in one environment does not
replace packages used by the other. Ruff, mypy, pytest, and coverage caches are also kept inside
the container. `ui/node_modules` and `ui/.next` also use DevContainer volumes, so its Next.js
output does not replace host output. Recreate the DevContainer after changing these mounts; its
first `uv sync` installs dependencies into the new volume.

Then attach to the container using VS Code's DevContainer extension or:

```shell
docker compose -f compose.devcontainer.yaml exec --user vscode devcontainer zsh
```

Check the Git identity inside the container before committing because host-level Git settings are
not copied into the DevContainer automatically:

```shell
git config --global user.name
git config --global user.email
```

Set them in the container if either command is empty.

## Nix Host Shell

Nix can provide the local CLI toolchain without starting the DevContainer. This is useful when
you want to run Python tests, UI checks, or Docker Compose tasks from the host shell while keeping
the service stack in Docker.

Install [Nix](https://nixos.org/download/) with flakes enabled, then enter the development shell:

```shell
nix develop
```

The shell provides Python 3.11, uv, Bun, Node.js 24, go-task, Docker CLI/Compose, jq, PostgreSQL
client tools, and the secret scanning tools used by the project. It also sets `UV_PYTHON` to the
Nix-provided Python 3.11 so `uv sync` does not accidentally select Python 3.12 on macOS, where
some workflow backend dependencies may fail to build. It does not start MongoDB, PostgreSQL,
Prefect, API, or UI services by itself; use the existing Docker Compose tasks for those services.

After entering the Nix shell for the first time, install project dependencies:

```shell
task dev-local-setup
```

Continue with [Run the Development Stack](#run-the-development-stack).

## Refresh Dependencies

The DevContainer includes Lychee and installs Python, frontend, and Lefthook dependencies during
creation. To refresh dependencies and install the local documentation checker manually, run:

```shell
task dev-local-setup
```

The setup task installs Lychee in `$HOME/.local/bin` when the active environment does not already
provide the pinned version. Keep that directory on `PATH` when running host-side tasks outside the
DevContainer or Nix shell.

## Run the Development Stack

```shell
task dev-local
```

This starts the supporting services in Docker Compose and runs the API and UI with hot reload,
on the host or in the DevContainer. Use this flow when editing backend or frontend code
frequently. The `caddy` service of the Compose deployment serves the browser on `UI_PORT` with
the same Caddyfile, so `/api`, `/prefect` with its sign-in check, and the Copilot chat stream
behave as in production.

The component tasks are:

- `task dev-services`: start Caddy, MongoDB, PostgreSQL, Prefect, deployment-service,
  user-flow-worker, and the Pi Agent Runtime, adding `compose.dev-local.yaml`, which points Caddy
  at the API and UI below and publishes MongoDB (`MONGO_PORT`), Prefect (`PREFECT_PORT`), the
  deployment service (`DEPLOYMENT_SERVICE_PORT`), and the runtime (`AGENT_RUNTIME_PORT`, default
  `8002`) on `127.0.0.1`
- `task dev-api-local`: run the FastAPI app with `--reload` on `API_PORT`
- `task dev-ui-local` (or `task dev-ui`): run `next dev` on `UI_DEV_PORT`, default `5713`, behind
  Caddy; it needs `task dev-services` running

| Service | URL |
| --- | --- |
| QDash UI | http://localhost:5714 |
| API Documentation | http://localhost:5714/api/docs |
| Prefect Dashboard | http://localhost:5714/prefect/ (signed in) |

Two development stacks on one host also need distinct `API_PORT`, `UI_DEV_PORT`, and the
loopback ports above. On macOS the API and Next.js listen on `127.0.0.1`. On a Linux host they
listen on `0.0.0.0` so that Caddy can reach them through the Docker host gateway, which also
exposes them to the local network; set `QDASH_DEV_BIND` to narrow this. A DevContainer created
before this setting existed must be recreated so that `QDASH_DEV_HOST` is set; see
[how Caddy reaches the development servers](./architecture.md#browser-entry-point).
`task dev-local-down` stops the host processes and the services with the same overlay.

Use [Developer Commands](./commands.md) for linting, tests, builds, generation,
and documentation tasks. Use [Operator Setup](../user-guide/setup.md) when you need the full
Compose deployment rather than the host-side development stack.

## Secret Scanning Tools

The DevContainer and [Nix host shell](#nix-host-shell) provide Betterleaks, Trufflehog, and
Lefthook. Checks and commits require the
[pinned Betterleaks release](./conventions/credential-scan.md#scanner-version); run them inside
one of these environments.

Enable the git hooks from the Nix shell or the DevContainer:

```shell
lefthook install
```

> The pre-commit hook requires the pinned Betterleaks release. Commit from the Nix shell (`nix develop -c git commit`) or the DevContainer; with a missing or different release, commits fail closed instead of bypassing the staged leak scan.
