# Operator Setup

QDash can run as a full Docker Compose stack or as a host-side API/UI connected to Docker-backed
services. Operators normally use the Docker Compose stack; developers usually use the host-side
stack.

## Qubex Setup

Create `.env` from the Qubex example when you want QDash to run with the Qubex backend:

```bash
cp .env.example.qubex .env
```

Review or fill in these values before starting services:

| Variable | Purpose |
| --- | --- |
| `ENV` | Environment label; keep `dev-qubex` for local Qubex-backed setup unless you need another label |
| `DEFAULT_BACKEND` | Backend selected by default; keep `qubex` for the Qubex-backed stack |
| `QDASH_ADMIN_USERNAME` / `QDASH_ADMIN_PASSWORD` | Initial admin login |
| `API_PORT` / `UI_PORT` / `PREFECT_PORT` | Host ports for API, UI, and Prefect |
| `MONGO_DATA_PATH` / `POSTGRES_DATA_PATH` | Persistent database storage |
| `CALIB_DATA_PATH` | Calibration figures and run artifacts |
| `CALIB_TASKS_PATH` | Calibration task definitions used by the workflow worker |
| `CONFIG_PATH` | Qubex backend configuration repository/data |
| `CONFIG_REPO_URL` / `GITHUB_TOKEN` / `GITHUB_USER` | Optional Qubex config repository sync settings |
| `CLIENT_URL` | Public UI URL when the app is served through a domain or tunnel |
| `TUNNEL_TOKEN` | Optional Cloudflare Tunnel token for remote access |
| `QDASH_API_TOKEN` | Optional API token for automation or service-to-service access |
| `OPENAI_API_KEY` / `OLLAMA_BASE_URL` / `OLLAMA_API_KEY` | Optional Copilot AI provider settings |
| `KNOWLEDGE_REPO_URL` | Optional external knowledge repository for Copilot context |
| `ENABLE_LOCAL_CODEX_AGENT` | Optional local-only workflow editing bridge for Host Codex; keep `false` unless explicitly testing it |

QDash application settings are committed under `config/app`, `config/domain`, and
`config/copilot`; `CONFIG_PATH` is only for the Qubex backend configuration tree.

### Qubex Configuration Files

The Qubex backend requires hardware and parameter configuration files before calibration tasks can
run. Prepare a Qubex configuration tree following the
[Qubex system configuration guide](https://amachino.github.io/qubex/user-guide/getting-started/system-configuration/)
and place it under `CONFIG_PATH`.

QDash resolves Qubex files by chip ID, so the expected local layout is:

```text
config/qubex-config/
  <chip_id>/
    config/
      chip.yaml
      box.yaml
      system.yaml
      wiring.yaml
      skew.yaml
    params/
      measurement_defaults.yaml
      ...
    calibration/
      calib_note.json
```

For the default `.env.example.qubex`, `CONFIG_PATH="./config/qubex-config"`. A task for
`chip_id="64Qv3"` therefore reads shared Qubex files from
`./config/qubex-config/64Qv3/config` and parameter files from
`./config/qubex-config/64Qv3/params`. `skew.yaml` is only needed for Qubex setups that require
inter-box timing adjustment.

### Repository-Managed Qubex Config

If the Qubex configuration tree is managed in a Git repository, set the repository settings in
`.env`:

```bash
CONFIG_REPO_URL=https://github.com/<owner>/<qubex-config-repo>.git
GITHUB_USER=<github-username>
GITHUB_TOKEN=<github-token>
```

With these values set, QDash can keep `CONFIG_PATH` synchronized with the repository. Calibration
sessions pull the latest config before running when GitHub pull is enabled, which is the default
for Qubex workflows. Config changes can also be pulled or pushed from the file management UI.

When workflow GitHub push is enabled, QDash can commit updated calibration files such as
`calibration/calib_note.json` and parameter YAML files back to the config repository after a
calibration run.

Complete the Qubex config placement or repository setup before starting services with
`task deploy-local` or `task dev-local`.

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

Stop the host API/UI processes and Docker Compose services:

```bash
task dev-local-down
```

## Remote Access

Set `TUNNEL_TOKEN` in `.env`, then run:

```bash
task deploy
```

This starts the Compose stack with the Cloudflare tunnel profile.
