# Development Environment Setup

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
| [Python](https://www.python.org/downloads/) | 3.11-3.12 | Backend development                  |
| [Bun](https://bun.sh/)                      | 1.0+      | Frontend package manager and runtime |
| [Node.js](https://nodejs.org/)              | 20+       | Alternative frontend runtime         |

## Getting Started

### Clone the Repository

```shell
git clone https://github.com/oqtopus-team/qdash.git
cd qdash
```

### Initial Setup

Create the environment file from the example:

```shell
cp .env.example .env
```

Data directories are created by Docker Compose and `task dev-local-setup` as needed. Edit `.env`
before starting services if you need custom ports, data paths, or admin credentials.

### Using DevContainer (Recommended)

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

### Using Nix (Lightweight Host Shell)

Nix can provide the local CLI toolchain without starting the DevContainer. This is useful when
you want to run Python tests, UI checks, or Docker Compose tasks from the host shell while keeping
the service stack in Docker.

Install [Nix](https://nixos.org/download/) with flakes enabled, then enter the development shell:

```shell
nix develop
```

The shell provides Python 3.11, uv, Bun, Node.js 20, go-task, Docker CLI/Compose, jq, PostgreSQL
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
Docker Compose, then runs the API and UI on the host. The UI is available through the reverse proxy
at `http://dev-fake.qdash.test:${PROXY_PORT}`.

### Install Dependencies

The DevContainer installs Python, frontend, and Lefthook dependencies automatically during
creation. To refresh dependencies manually, run:

```shell
task dev-local-setup
```

## Running Services

### Full Docker Compose Stack

```shell
task deploy-local
```

This starts the following services:

- **mongo**: MongoDB database (port 27017)
- **mongo-express**: MongoDB admin UI (port 8081)
- **postgres**: PostgreSQL database (port 5432)
- **prefect-server**: Prefect workflow server (port 4200)
- **deployment-service**: Prefect deployment management
- **user-flow-worker**: User flow execution worker
- **api**: FastAPI backend (port 5715)
- **ui**: Next.js frontend (port 5714)

### Lightweight Host Stack

```shell
task dev-local
```

This starts the supporting services in Docker Compose and runs the API and UI directly on the
host. Use this flow when editing backend or frontend code frequently. The reverse proxy also starts
and routes the same local hostnames to the host-side API and UI processes.

The component tasks are:

- `task dev-services`: start MongoDB, PostgreSQL, Prefect, deployment-service, and user-flow-worker
- `task dev-api-local`: run the FastAPI app on the host against Docker services
- `task dev-ui-local`: run the Next.js app on the host against the local API

When running multiple local Docker Compose instances, update `.env` with instance-specific ports
before starting the stack. `task dev-local` and `task deploy-local` run this assignment
automatically:

```shell
task deploy-local
```

`ENV` is the short application environment label and is used for local hostnames.
`QDASH_INSTANCE` defaults to `${ENV}-qdash` and is used for the Compose project name. The default
`.env` uses `ENV="dev-fake"` and `QDASH_INSTANCE=dev-fake-qdash`, so Docker resources are scoped by
the instance while local URLs stay short. The assignment task derives `COMPOSE_PROJECT_NAME`,
reverse-proxy hostnames, service ports, and public URLs from these values. Existing assigned ports
are kept on later deploys for the same instance.

The Compose stack includes a Caddy reverse proxy. For `ENV="dev-fake"`, the proxied
URLs are `http://dev-fake.qdash.test:${PROXY_PORT}`,
`http://api.dev-fake.qdash.test:${PROXY_PORT}`,
`http://prefect.dev-fake.qdash.test:${PROXY_PORT}`, and
`http://mongo.dev-fake.qdash.test:${PROXY_PORT}`. These URLs work for both `task dev-local` and
`task deploy-local`; the direct service ports remain available in these local tasks for tools that
connect to MongoDB, PostgreSQL, or the API directly. `task deploy` does not publish these service
ports; Cloudflare Tunnel reaches the reverse proxy through Docker networking at
`http://reverse-proxy:80`.

The main UI hostname also proxies `/api/*` to the API, so frontend traffic can stay on one origin.

For server environments that should also be reachable through SSH port forwarding, set
`QDASH_LOCAL_DOMAIN` once for the local wildcard DNS zone. `QDASH_LOCAL_HOST` defaults to
`${ENV}.${QDASH_LOCAL_DOMAIN}` and only needs to be set when the local alias should differ
from that pattern. `task deploy` resolves templated URL values before starting Compose: `CLIENT_URL`
defaults to `https://${QDASH_HOST}`, `NEXT_PUBLIC_API_URL` defaults to `/api`, and
`NEXT_PUBLIC_PREFECT_URL` defaults to `http://prefect.${QDASH_LOCAL_HOST}:${PROXY_PORT}`.
`task deploy` keeps the Cloudflare Tunnel setup and publishes only the reverse proxy on
`127.0.0.1:${PROXY_PORT}`. Forward it from the workstation with a matching local port:

```shell
ssh -L 18080:127.0.0.1:18080 anemone
```

Then open `http://${ENV}.qdash.test:18080`.
Configure local wildcard DNS once so `*.${QDASH_LOCAL_DOMAIN}` resolves to `127.0.0.1`; this avoids per-host
`/etc/hosts` entries and does not depend on public DNS.

On macOS with Homebrew:

```shell
brew install dnsmasq
mkdir -p "$(brew --prefix)/etc/dnsmasq.d"
echo 'address=/.qdash.test/127.0.0.1' | sudo tee "$(brew --prefix)/etc/dnsmasq.d/qdash.conf"
sudo mkdir -p /etc/resolver
echo 'nameserver 127.0.0.1' | sudo tee /etc/resolver/qdash.test
sudo brew services start dnsmasq
```

When running multiple QDash environments on one server, keep `ENV`, the Docker Compose project name,
forwarded proxy port, local alias, public hostname, and data paths unique for each environment. The
internal service ports such as `API_PORT=5715` and `UI_PORT=5714` may stay the same because they are
not published directly by `task deploy`.

```env
# qdash-dev
ENV=dev
QDASH_INSTANCE=dev-qdash
QDASH_LOCAL_DOMAIN=qdash.test
QDASH_HOST=qdash-dev.qiqb.dev
PROXY_PORT=18080
POSTGRES_DATA_PATH=./postgres_data_dev
MONGO_DATA_PATH=./mongo_data_dev/data/db

# qdash-stg
ENV=stg
QDASH_INSTANCE=stg-qdash
QDASH_LOCAL_DOMAIN=qdash.test
QDASH_HOST=qdash-stg.qiqb.dev
PROXY_PORT=18081
POSTGRES_DATA_PATH=./postgres_data_stg
MONGO_DATA_PATH=./mongo_data_stg/data/db
```

Forward both environments from the workstation when needed:

```shell
ssh -L 18080:127.0.0.1:18080 -L 18081:127.0.0.1:18081 anemone
```

### Access Points

| Service           | URL                                             |
| ----------------- | ----------------------------------------------- |
| QDash UI          | `http://${ENV}.qdash.test:${PROXY_PORT}`         |
| API Documentation | `http://api.${ENV}.qdash.test:${PROXY_PORT}/docs` |
| Prefect Dashboard | `http://prefect.${ENV}.qdash.test:${PROXY_PORT}` |
| MongoDB Admin     | `http://mongo.${ENV}.qdash.test:${PROXY_PORT}`   |

## Development Commands

### Using go-task

```shell
# Show all available tasks
task

# Start the full Docker Compose stack
task deploy-local

# Start supporting services with host API/UI
task dev-local

# Deploy with Cloudflare Tunnel
task deploy

# Restart API service
task restart-api
```

### Code Quality

```shell
# Auto-fix Python and UI lint/format issues
task lint

# Auto-fix Python only
task lint-python

# Auto-fix UI only
task lint-ui

# Check Python linting and formatting without modifying files
task ci-lint

# Run mypy type checking
task ci-typecheck
```

### Testing

```shell
# Run all tests
task test

# Run API tests only
task test-api

# Run workflow tests only
task test-workflow

# Run UI tests only
task test-ui

# Run tests with coverage
task test-coverage

# Run tests, stop on first failure
task test-fast
```

### Build & Generate

```shell
# Generate TypeScript API client
task generate

# Build UI
task build

# Build API Docker image
task build-api

# Build workflow Docker image
task build-workflow

# Check dependency locks
task check-locks
```

### Documentation

```shell
# Start docs dev server
task docs

# Build docs
task build-docs

# Generate DB schema docs
task tbls-docs
```

## Secret Scanning Tools

DevContainer users are automatically set up with Gitleaks, Trufflehog, and Lefthook. For local development outside the DevContainer, install the tools manually:

**macOS:**

```shell
brew install gitleaks trufflehog lefthook
```

**Linux:**

Download binaries from GitHub Releases:

- [Gitleaks Releases](https://github.com/gitleaks/gitleaks/releases)
- [Trufflehog Releases](https://github.com/trufflesecurity/trufflehog/releases)
- [Lefthook Releases](https://github.com/evilmartians/lefthook/releases)

After installing the tools, enable the git hooks:

```shell
lefthook install
```

> Lefthook gracefully skips if the binary is not found, so environments without it (e.g., Windows without manual install) will not be blocked.

## Environment Variables

Key environment variables are configured in `.env`. See `.env.example` for available options:

| Variable                  | Default | Description                 |
| ------------------------- | ------- | --------------------------- |
| `PROXY_PORT`              | 18080   | Reverse proxy port          |
| `API_PORT`                | 5715    | Backend API port            |
| `UI_PORT`                 | 5714    | Frontend UI port            |
| `QDASH_INSTANCE`          | -       | Optional instance name; defaults to `${ENV}-qdash` |
| `MONGO_PORT`              | 27017   | MongoDB port                |
| `POSTGRES_PORT`           | 5432    | PostgreSQL port             |
| `PREFECT_PORT`            | 4200    | Prefect dashboard port      |
| `DEPLOYMENT_SERVICE_PORT` | 4006    | Deployment service port     |
| `CALIB_DATA_PATH`         | -       | Calibration data mount path |
| `CALIB_TASKS_PATH`        | -       | Calibration tasks path      |
| `CONFIG_PATH`             | -       | Qubex backend config repository/data path |
| `NEXT_PUBLIC_API_URL`     | -       | Public API URL for frontend |
| `NEXT_PUBLIC_PREFECT_URL` | -       | Prefect dashboard URL       |
| `NEXT_ALLOWED_DEV_ORIGINS` | -       | Additional hostnames allowed to access the Next.js dev server |
