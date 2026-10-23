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
| [Caddy](https://caddyserver.com/docs/install) | 2.10.2 | Host-side browser gateway (`task dev-proxy-local`) |
| [Node.js](https://nodejs.org/) | 24.22.1+ (24.x) or 26.12.1+ | Next.js production runtime |

## Clone the Repository

```bash
git clone https://github.com/oqtopus-team/qdash.git
cd qdash
```

A DevContainer can start without `.env`. Before running Qubex-backed calibration tasks, follow
[Operator Setup](../user-guide/setup.md) for `.env` and `CONFIG_PATH` configuration.

## DevContainer

The recommended way to develop is using the DevContainer:

```shell
docker compose -f compose.devcontainer.yaml up -d
```

The DevContainer can start without a local `.env`; Docker Compose uses `.env` when present. The
checked-in VS Code configuration runs its remote session as the `vscode` user so files created in
the checkout remain writable from the host. Docker Compose direct sessions can still use `root`
when needed.

On Linux, build the `vscode` user with the host UID and GID so files created in the checkout
remain writable from both the host and the container:

```shell
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
checkout and use the same Docker daemon. Run development commands as the `vscode` user in the
DevContainer; reserve root for container setup.

The DevContainer Compose service publishes `UI_PORT` on the host as soon as it starts, even before
its Caddy process runs. Stop the DevContainer before starting the full Compose stack at the same
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

The shell provides Python 3.11, uv, Bun, Node.js 24, go-task, Caddy, Docker CLI/Compose, jq,
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
the `compose.host.yaml` override, then runs the API, UI, and Caddy on the host. Caddy is the
browser entry point at <http://localhost:5714>; the UI and API listen behind it on ports `5716`
and `5715`. The Prefect host port is `4200` for service-to-service development, while browser
access uses `/prefect` through Caddy. Caddy must be available on `PATH`; DevContainers install
Caddy 2.10.2 and the Nix shell provides it. Install Caddy on the host when running these tasks
outside either environment.

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
runs the API, UI, and Caddy on the host. Use this flow when editing backend or frontend code
frequently. Open the browser through Caddy at `http://localhost:5714`; do not use the service
ports as browser entry points.

The component tasks are:

- `task dev-services`: start MongoDB, PostgreSQL, Prefect, deployment-service, and user-flow-worker
- `task dev-api-local`: run the FastAPI app on the host against Docker services
- `task dev-ui-local`: run the Next.js app on the host against the local API
- `task dev-proxy-local`: run Caddy as the browser entry point

The host task defaults are `UI_PORT=5714`, `API_PORT=5715`, `UI_INTERNAL_PORT=5716`, and
`PREFECT_PORT=4200`. Browser traffic enters at `5714`; the other listeners serve the host
development processes and are not browser entry points. `task dev-proxy-local` accepts these
gateway settings from `.env`:

The example `.env` leaves `PREFECT_API_URL` blank so `task dev-api-local` can choose its context:
host tasks use `http://127.0.0.1:<PREFECT_PORT>/prefect/api`, while DevContainer tasks use
`http://prefect-server:4200/prefect/api`. Compose services also use the internal Prefect service
address. Set an explicit `PREFECT_API_URL` only when overriding that context default, and keep the
`/prefect/api` path.

| Variable | Purpose | Default |
| --- | --- | --- |
| `CADDY_LOCAL_SITE_ADDRESS` | Host Caddy site address | `http://localhost:<UI_PORT>` |
| `CADDY_LOCAL_BIND_ADDRESS` | Host Caddy bind address | `127.0.0.1` |
| `CADDY_SITE_ADDRESS` | Caddy site address | Host task derives this from `CADDY_LOCAL_SITE_ADDRESS`; `:80` in Compose or `CLIENT_URL` for HTTPS |
| `CADDY_BIND_ADDRESS` | Network address Caddy listens on | `127.0.0.1` in the host task; `0.0.0.0` in Compose |
| `CADDY_UI_UPSTREAM` | UI server address | `127.0.0.1:<UI_INTERNAL_PORT>` for host development |
| `CADDY_API_UPSTREAM` | API server address | `127.0.0.1:<API_PORT>` for host development |
| `CADDY_PREFECT_UPSTREAM` | Prefect server address | `127.0.0.1:<PREFECT_PORT>` for host development |
| `CADDY_TRUSTED_PROXIES` | Proxies trusted to supply forwarded client headers | `127.0.0.1/32 ::1/128` |

Compose uses the service-name upstreams `ui:5714`, `api:<API_PORT>`, and
`prefect-server:4200`. Only trust the addresses of an actual TLS-terminating proxy in
`CADDY_TRUSTED_PROXIES`.

### Access Points

| Browser destination | URL |
| --- | --- |
| QDash UI | `http://localhost:5714/` |
| API documentation | `http://localhost:5714/api/docs` |
| Prefect dashboard | `http://localhost:5714/prefect/dashboard` |

The local API and UI listeners use `API_PORT` (default `5715`) and `UI_INTERNAL_PORT` (default
`5716`). The host override also binds MongoDB, Prefect, and the deployment service to loopback for
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

DevContainer users are automatically set up with Betterleaks, Trufflehog, and Lefthook. For local development outside the DevContainer, install the tools manually:

**macOS:**

```shell
brew install betterleaks trufflehog lefthook
```

**Linux:**

Download binaries from GitHub Releases:

- [Betterleaks Releases](https://github.com/betterleaks/betterleaks/releases)
- [Trufflehog Releases](https://github.com/trufflesecurity/trufflehog/releases)
- [Lefthook Releases](https://github.com/evilmartians/lefthook/releases)

After installing the tools, enable the git hooks:

```shell
lefthook install
```

> The pre-commit hook requires Betterleaks. Install it before enabling Lefthook; otherwise commits fail closed instead of bypassing the staged leak scan.
