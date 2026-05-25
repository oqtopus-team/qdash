# Operator Setup

QDash can run as a full Docker Compose stack or as a host-side API/UI connected to Docker-backed
services. Operators normally use the Docker Compose stack; developers usually use the host-side
stack.

## Environment File

Create `.env` from the example:

```bash
cp .env.example .env
```

Review these values before starting services:

| Variable | Purpose |
| --- | --- |
| `QDASH_ADMIN_USERNAME` / `QDASH_ADMIN_PASSWORD` | Initial admin login |
| `API_PORT` / `UI_PORT` / `PREFECT_PORT` | Host ports for API, UI, and Prefect |
| `MONGO_DATA_PATH` / `POSTGRES_DATA_PATH` | Persistent database storage |
| `CALIB_DATA_PATH` | Calibration figures and run artifacts |
| `CONFIG_PATH` | Qubex backend configuration repository/data |
| `DEFAULT_BACKEND` | Backend selected by default |

QDash application settings are committed under `config/app`, `config/domain`, and
`config/copilot`; `CONFIG_PATH` is only for the Qubex backend configuration tree.

## Full Stack

Start all services:

```bash
task deploy-local
```

Open:

- QDash UI: <http://localhost:5714/login>
- API docs: <http://localhost:5715/docs>
- Prefect: <http://localhost:4200>

## Host-Side Stack

For local iteration with API/UI running on the host:

```bash
task dev-local-setup
task dev-local
```

This starts MongoDB, PostgreSQL, Prefect, deployment-service, and user-flow-worker in Docker,
then runs the API and UI on the host.

## Remote Access

Set `TUNNEL_TOKEN` in `.env`, then run:

```bash
task deploy
```

This starts the Compose stack with the Cloudflare tunnel profile.
Configure Cloudflare Tunnel public hostnames to forward to `http://reverse-proxy:80`. The main
hostname serves the UI and `/api/*`; optional Prefect and Mongo Express hostnames can use the same
service URL for operator-only access.
`task deploy` validates the tunnel token and reverse-proxy hostname settings before starting the
stack; it does not rewrite `.env`.

For multiple QDash environments on the same server, give each environment a unique
`COMPOSE_PROJECT_NAME`, `QDASH_HOST`, `QDASH_LOCAL_HOST`, `PROXY_PORT`, and database data path. The
application service ports can stay at their defaults because `task deploy` publishes only the
reverse proxy on `127.0.0.1:${PROXY_PORT}` for SSH forwarding.

```env
ENV=dev-qdash
COMPOSE_PROJECT_NAME=dev-qdash
QDASH_HOST=qdash-dev.qiqb.dev
QDASH_LOCAL_HOST=dev-qdash.localhost
CLIENT_URL=https://qdash-dev.qiqb.dev
PROXY_PORT=18080
POSTGRES_DATA_PATH=./postgres_data_dev
MONGO_DATA_PATH=./mongo_data_dev/data/db
```
