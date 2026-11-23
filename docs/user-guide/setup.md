# Setup

Install QDash with Docker Compose, then sign in and run a calibration.

## Choose a Backend

Use [Fake](./setup/fake-backend.md) to try QDash without hardware, or
[Qubex](./setup/qubex-backend.md) for a supported lab setup. For host-side code development,
use [developer setup](../developer-guide/setup.md).

## Prepare the Host

Install Git and Docker with Compose v2.24.4 or later. Start the Docker daemon
(on macOS, open Docker Desktop or your Docker provider), then clone the stable branch:

```bash
git clone --branch main https://github.com/oqtopus-team/qdash.git
cd qdash
```

## Create the Environment File

For Fake:

```bash
cp .env.example .env
```

For Qubex:

```bash
cp .env.example.qubex .env
```

For Qubex, [prepare the configuration tree](./setup/qubex-backend.md) before startup.

## Configure Shared Deployment Settings

Set a unique administrator password in `.env`. The examples otherwise work for a first local start.

| Variable | Purpose |
| --- | --- |
| `QDASH_ADMIN_USERNAME`, `QDASH_ADMIN_PASSWORD` | Initial administrator credentials |
| `ENV` | Deployment and Compose project name |
| `UI_PORT` | Published port; default `5714` |
| `MONGO_DATA_PATH`, `POSTGRES_DATA_PATH` | Persistent database directories |
| `MONGO_VERSION` | MongoDB image release; example `9.0.8` is for empty data only |
| `CALIB_DATA_PATH` | Figures, raw data, and artifacts |
| `CLIENT_URL` | Public UI URL for links and redirects |

For existing MongoDB data, [pin its running release](./mongodb-upgrade.md) before starting.
Leave optional integration credentials empty until needed.

## Start QDash

```bash
docker compose config --quiet
docker compose up -d --build
```

With Go Task, `task deploy-local` also pulls the configured knowledge repository.

## Verify the Installation

Run `docker compose ps --all`. Long-running services should be running, MongoDB should be healthy,
and the one-shot `calibration-migration` and `agent-runtime-auth` services should have exited
with code 0. If startup fails, read [service logs](./operations.md#inspect-logs) before continuing.

Open these addresses using your configured `UI_PORT`:

| Service | Default address |
| --- | --- |
| QDash | <http://localhost:5714/login> |
| API docs | <http://localhost:5714/api/docs> |
| Prefect | <http://localhost:5714/prefect/dashboard> |

Sign in with the administrator credentials. QDash creates a default project for that account.
Only `UI_PORT` is exposed; use [Operations](./operations.md) for logs and database access.

## Next Steps

[Run your first calibration](./first-calibration.md). On hardware, confirm the chip's configuration
before starting a task.

## Optional Settings

### Configure AI

<a id="authenticate-ai-endpoints-with-cloudflare-access"></a>

Follow [AI Setup](./setup/ai.md) for chat, evaluations, classifiers, and endpoint authentication.

### Set the Default Color Theme

Set `NEXT_PUBLIC_DEFAULT_THEME` to a supported theme, such as `light` or `dark`, then rebuild:

```bash
docker compose build ui
docker compose up -d ui
```

A browser's saved theme takes priority; an invalid value falls back to `light`.

### Limit Metric Script Runs

Set limits in `.env`, then run `docker compose up -d api metric-runner`. Deploy both services
from the same revision. Leave `METRIC_RUNNER_MODE` unset for container isolation.

| Variable | Default |
| --- | --- |
| `METRIC_SCRIPT_TIMEOUT_SECONDS` | `60` |
| `METRIC_SCRIPT_MEMORY_MB` | `1024` |
| `METRIC_RUNNER_CONCURRENCY` | `2` |
| `METRIC_RUNNER_QUEUE_LIMIT` | `16` |
| `METRIC_RUNNER_QUEUE_WAIT_SECONDS` | `5` |
| `METRIC_RUNNER_MAX_TIMEOUT_SECONDS` | `300` |
| `METRIC_RUNNER_MAX_MEMORY_MB` | `1024` |
| `METRIC_RUNNER_MEMORY_LIMIT` | `3g` |
| `METRIC_RUNNER_CPU_LIMIT` | `2` |
| `METRIC_RUNNER_PIDS_LIMIT` | `256` |
| `METRIC_RUNNER_TMPFS_SIZE` | `256m` |

Keep the container memory above `concurrency × (max script MiB + 128) + 128 + tmpfs MiB`.
The defaults need 2688 MiB of 3 GiB. Check `docker compose logs metric-runner` after changes.
A stopped runner blocks validation, saves, and previews. These limits protect trusted editors'
runs; see the [isolation model](../developer-guide/architecture/metric-scripts.md) before granting
script access to untrusted users.

### Notify Experts of Agent Interventions in Slack

Set `SLACK_BOT_TOKEN`, `SLACK_AGENT_NOTIFICATION=true`, and `SLACK_AGENT_CHANNEL_ID`; the bot
must belong to the channel. Set `CLIENT_URL` and apply with `docker compose up -d api`.

The channel receives agent-session starts, ends, and expert requests for every project. Limit
its membership accordingly. Links still require QDash project access. Failed sends retry and
can occasionally duplicate; they do not change the recorded session or intervention.

### Run Several Deployments on One Host

Use separate checkouts, distinct `ENV` and `UI_PORT` values, and separate database and artifact
directories. Different Compose names alone do not separate data.

### Enable Remote Access

Configure the bundled tunnel in `.env`:

```dotenv
CLIENT_URL=https://qdash.example.com
TUNNEL_TOKEN=<cloudflare-tunnel-token>
COMPOSE_PROFILES=tunnel
```

Apply with `docker compose up -d --build`, or `task deploy`.
