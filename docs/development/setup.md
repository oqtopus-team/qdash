# Developer Setup

QDash development starts from a local repository checkout and uses either DevContainer or Nix for
the project toolchain.

## Prerequisites

### Required Tools

| Tool                                                       | Version | Description                              |
| ---------------------------------------------------------- | ------- | ---------------------------------------- |
| [Docker](https://docs.docker.com/get-docker/)              | -       | Container virtualization platform        |
| [Docker Compose](https://docs.docker.com/compose/install/) | v2.24+  | Management of multiple Docker containers |
| [go-task](https://taskfile.dev/installation/)              | v3.41+  | Task runner for development commands     |
| [uv](https://docs.astral.sh/uv/)                           | -       | Python package manager                   |

### Optional Tools (for local development)

| Tool                                        | Version   | Description                          |
| ------------------------------------------- | --------- | ------------------------------------ |
| [Python](https://www.python.org/downloads/) | 3.10-3.12 | Backend development                  |
| [Bun](https://bun.sh/)                      | 1.4.0+    | Frontend package manager and runtime |
| [Node.js](https://nodejs.org/)              | 24+       | Alternative frontend runtime         |

## Clone the Repository

```bash
git clone https://github.com/oqtopus-team/qdash.git
cd qdash
```

A DevContainer can start without `.env`. Before running Qubex-backed calibration tasks, follow
[Operator Setup](../operator-guide/setup.md) for `.env` and `CONFIG_PATH` configuration.

## DevContainer

The recommended way to develop is using the DevContainer:

```shell
docker compose -f compose.devcontainer.yaml up -d
```

The DevContainer can start without a local `.env`; Docker Compose uses `.env` when present.
When starting it with Docker Compose directly on Linux, pass the host UID and GID so files
generated in the mounted workspace remain writable from both the host and the container:

```shell
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose -f compose.devcontainer.yaml up -d --build
```

VS Code's Dev Containers extension also aligns the remote user's UID with the host by using
`updateRemoteUserUID`.
The container mounts `/var/run/docker.sock` so devcontainer users can run the local Docker
Compose tasks from inside the workspace. User-level tools installed under `/home/vscode/.local`
and Claude Code configuration under `/home/vscode/.claude` are persisted in Docker volumes, so
they survive container rebuilds.

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

Then start the lightweight development stack:

```shell
task dev-local
```

This starts MongoDB, PostgreSQL, Prefect, the deployment service, and the user flow worker with
Docker Compose, then runs the API and UI on the host. The UI is available at
<http://localhost:5714>.

Stop the host API/UI processes and Docker Compose services:

```shell
task dev-local-down
```

## Refresh Dependencies

The DevContainer installs Python, frontend, and Lefthook dependencies automatically during
creation. To refresh dependencies manually, run:

```shell
task dev-local-setup
```

## Run the Development Stack

```shell
task dev-local
```

This starts the supporting services in Docker Compose and runs the API and UI directly on the
host. Use this flow when editing backend or frontend code frequently.

The component tasks are:

- `task dev-services`: start MongoDB, PostgreSQL, Prefect, deployment-service, and user-flow-worker
- `task dev-api-local`: run the FastAPI app on the host against Docker services
- `task dev-ui-local`: run the Next.js app on the host against the local API

### Access Points

| Service           | URL                        |
| ----------------- | -------------------------- |
| QDash UI          | http://localhost:5714      |
| API Documentation | http://localhost:5715/docs |
| Prefect Dashboard | http://localhost:4200      |
| MongoDB Admin     | http://localhost:8081      |

Use [Developer Commands](../developer-guide/commands.md) for linting, tests, builds, generation,
and documentation tasks. Use [Operator Setup](../operator-guide/setup.md) when you need the full
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
