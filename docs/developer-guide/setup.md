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

The DevContainer bind-mounts the checkout at `/workspace/qdash` and, by default, its host parent
directory at `/workspace/repos`. Git changes and commits in QDash are visible from either
environment. With the default mount, clones made under `/workspace/repos` in the container appear
beside QDash on the host; clones made beside QDash on the host appear under `/workspace/repos` in
the container. For example, this creates a second checkout from the container:

```shell
git clone https://github.com/oqtopus-team/qdash.git /workspace/repos/qdash-copy
```

Use `/workspace/qdash` for QDash development so its dependencies stay in the separate
DevContainer volumes. The initial QDash clone must be made on the host because its Compose file
is needed to start the DevContainer. If you want a different shared directory, create it on the
host and export `QDASH_SHARED_REPOS_DIR` with its absolute path before starting the container.
The directory must already exist and be writable by your host user. No repository manager is
required. Setting the override only in `.env` does not pass it to the host-side preflight check.

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

The DevContainer Compose service publishes `UI_PORT` on the host as soon as it starts, even before
its UI process runs. Stop the DevContainer before starting the full Compose stack at the same
default `UI_PORT=5714`, or assign a different `UI_PORT` to one of the modes.

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

The shell provides Python 3.11, uv, Bun, Node.js 24, go-task, Docker CLI/Compose, jq,
PostgreSQL client tools, and the secret scanning tools used by the project. It also sets
`UV_PYTHON` to the Nix-provided Python 3.11 so `uv sync` does not accidentally select Python
3.12 on macOS, where some workflow backend dependencies may fail to build. It does not start
MongoDB, PostgreSQL, Prefect, API, or UI services by itself; use the existing Docker Compose
tasks for those services.

After entering the Nix shell for the first time, install project dependencies:

```shell
task dev-local-setup
```

Then start the lightweight development stack:

```shell
task dev-local
```

This starts MongoDB, PostgreSQL, Prefect, the deployment service, and the user flow worker with
the `compose.host.yaml` override, then runs the API and UI on the host. The UI is the browser
entry point at <http://localhost:5714>, and the Next.js development server proxies `/api` to the
API on port `5715` and `/prefect` to Prefect on port `4200`. This stack does not run Caddy, so you
do not need to install it on the host.

Stop the host API/UI processes and Docker Compose services:

```shell
task dev-local-down
```

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

This starts the supporting services in Docker Compose with loopback-only development ports and
runs the API and UI on the host. Use this flow when editing backend or frontend code
frequently. Open the browser at `http://localhost:5714`; do not use the service ports as browser
entry points.

The Next.js development server listens directly on `UI_PORT` and forwards `/api` to the API
(`INTERNAL_API_URL`) and `/prefect` to Prefect (`INTERNAL_PREFECT_URL`). Only the Compose stack
puts Caddy in front of QDash. As a result, host development skips the Caddy security headers and
the `/auth/prefect-access` check on `/prefect`; verify changes to either through the Compose stack.

The component tasks are:

- `task dev-services`: start MongoDB, PostgreSQL, Prefect, deployment-service, and user-flow-worker
- `task dev-api-local`: run the FastAPI app on the host against Docker services
- `task dev-ui-local`: run the Next.js app on `UI_PORT`, proxying `/api` and `/prefect`

The host task defaults are `UI_PORT=5714`, `API_PORT=5715`, and `PREFECT_PORT=4200`. Browser
traffic enters at `5714`; the other listeners serve the host development processes and are not
browser entry points.

`task dev-ui-local` listens on `127.0.0.1` on the host and on `0.0.0.0` in the DevContainer, where
Compose publishes the port on loopback. `INTERNAL_PREFECT_URL` defaults to
`http://127.0.0.1:<PREFECT_PORT>` on the host and `http://prefect-server:4200` in the DevContainer;
set it in the environment only to override that default.

Before it starts the UI, `task dev-ui-local` checks whether anything already accepts connections on
`UI_PORT` at `127.0.0.1` or `::1`, and exits with an error if so. An old UI that listens on all
interfaces does not block a new listener on `127.0.0.1`, so without this check `localhost` could
keep serving the old UI. Stop the old stack with `task dev-local-down`, or with
`docker compose down` for a Compose stack, and start again.

The example `.env` leaves `PREFECT_API_URL` blank so `task dev-api-local` can choose its context:
host tasks use `http://127.0.0.1:<PREFECT_PORT>/prefect/api`, while DevContainer tasks use
`http://prefect-server:4200/prefect/api`. Compose services also use the internal Prefect service
address. Set an explicit `PREFECT_API_URL` only when overriding that context default, and keep the
`/prefect/api` path.

### Caddy Settings

Compose passes every Caddy setting to `config/caddy/Caddyfile`, which has no defaults of its own.
The example `.env` files set no `CADDY_*` variable; add one to `.env` only to override its default.

Compose (`compose.yaml`) reads these variables:

| Variable | Purpose | Compose default |
| --- | --- | --- |
| `CADDY_SITE_ADDRESS` | Caddy site address | `:80`; `compose.https.yaml` sets it from `CLIENT_URL` |
| `CADDY_BIND_ADDRESS` | Network address Caddy listens on | `0.0.0.0` |
| `CADDY_UI_UPSTREAM` | UI server address | `ui:5714` |
| `CADDY_API_UPSTREAM` | API server address | `api:<API_PORT>` |
| `CADDY_PREFECT_UPSTREAM` | Prefect server address | `prefect-server:4200` |
| `CADDY_TRUSTED_PROXIES` | Proxies trusted to supply forwarded client headers | `127.0.0.1/32 ::1/128` |

Only trust the addresses of an actual TLS-terminating proxy in `CADDY_TRUSTED_PROXIES`.

### Access Points

| Browser destination | URL |
| --- | --- |
| QDash UI | `http://localhost:5714/` |
| API documentation | `http://localhost:5714/api/docs` |
| Prefect dashboard | `http://localhost:5714/prefect/dashboard` |

The local API and UI listeners use `API_PORT` (default `5715`) and `UI_PORT` (default `5714`).
The host override also binds MongoDB, Prefect, and the deployment service to loopback for
the development processes. `task dev-local-down` stops the host processes and the Compose stack
using the same `compose.yaml` and `compose.host.yaml` files.

Run each process task separately when needed. `task dev-services` and `task dev-local-down` both
use the host override; do not use plain `docker compose down` to stop that development stack.

For individual access to MongoDB, PostgreSQL, or Mongo Express during local administration, add
`compose.admin.yaml` and activate its `admin` profile:

```shell
docker compose -f compose.yaml -f compose.admin.yaml --profile admin up -d
docker compose -f compose.yaml -f compose.admin.yaml --profile admin down
```

These extra ports bind to loopback. Mongo Express is available at `http://localhost:8081` while
the profile is active. Keep the same `-f` files and profile on startup and shutdown.

The normal Compose deployment publishes only Caddy. Its internal API, database, and Prefect
services are reached through the Compose network. For public HTTPS, use the procedure in
[Operator Setup](../user-guide/setup.md#serve-qdash-over-https).

Use [Developer Commands](./commands.md) for linting, tests, builds, generation,
and documentation tasks. Use [Operator Setup](../user-guide/setup.md) when you need the full
Compose deployment rather than the host-side development stack.

## Secret Scanning Tools

The DevContainer and the [Nix host shell](#nix-host-shell) provide Betterleaks, Trufflehog, and Lefthook. Both pin Betterleaks to `BETTERLEAKS_VERSION` in `.devcontainer/Dockerfile`, and every leak scan rejects any other release; see [scanner version](./conventions/credential-scan.md#scanner-version). A Betterleaks installed by Homebrew or from the latest GitHub release is usually newer and fails that check, so on the host run checks and commits through `nix develop`.

Enable the git hooks from the Nix shell or the DevContainer:

```shell
lefthook install
```

> The pre-commit hook requires the pinned Betterleaks release. Commit from the Nix shell (`nix develop -c git commit`) or the DevContainer; with a missing or different release, commits fail closed instead of bypassing the staged leak scan.
