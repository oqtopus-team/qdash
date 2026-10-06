# Operator Setup

QDash operators configure the Qubex integration and run the full Docker Compose stack. Host-side
API and UI processes are documented in [Development Environment Setup](../development/setup.md).
Install Docker with Docker Compose and `uv` on the host. Go Task is optional for operators.

## Clone the Repository

Clone the Git repository's release branch. The repository default is `develop`, so select `main`
explicitly for an installation that will use Admin UI system updates:

```bash
git clone --branch main https://github.com/oqtopus-team/qdash.git
cd qdash
```

The `main` branch represents the latest stable release and its release commits carry
`vMAJOR.MINOR.PATCH` tags. Do not use `develop`, a feature branch, or a prerelease tag for an
updatable installation. The installation directory can be anywhere. See
[System Updates](./system-updates.md#git-branch-and-tag-requirements) for the complete update rules.

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
| `NEXT_PUBLIC_DEFAULT_THEME` | Initial UI color theme for browsers without a saved preference; defaults to `light` |
| `MONGO_DATA_PATH` / `POSTGRES_DATA_PATH` | Persistent database storage |
| `CALIB_DATA_PATH` | Calibration figures and run artifacts |
| `CALIB_TASKS_PATH` | Calibration task definitions used by the workflow worker |
| `CONFIG_PATH` | Qubex backend configuration repository/data |
| `CONFIG_REPO_URL` / `GITHUB_TOKEN` / `GITHUB_USER` | Optional Qubex config repository sync settings |
| `CLIENT_URL` | Public UI URL when the app is served through a domain or tunnel; Copilot also builds the links in its answers from it |
| `TUNNEL_TOKEN` | Optional Cloudflare Tunnel token for remote access |
| `QDASH_API_TOKEN` | Optional API token for automation or service-to-service access |
| `AGENT_RUNTIME_TOKEN` | Shared secret for QDash API/workers to call the internal Pi Agent Runtime; required when `copilot_backend: pi`, and requests fail closed when it is empty |
| `COMPOSE_PROFILES` | Set to `agent-runtime` when `copilot_backend: pi`; otherwise the Agent Runtime container is not created |
| `AGENT_RUNTIME_ENABLE_WRITE_TOOLS` | Experimental; set to `true` to expose the reviewed QDash write tools to Copilot (default: `false`) |
| `OPENAI_COMPATIBLE_BASE_URL` / `OPENAI_COMPATIBLE_API_KEY` | Base URL and credential for the default vendor-neutral OpenAI Chat Completions endpoint |
| `OPENAI_API_KEY` / `OLLAMA_BASE_URL` / `OLLAMA_API_KEY` | Optional settings for other Copilot AI providers |
| `KNOWLEDGE_REPO_URL` | Optional external knowledge repository for Copilot context |
| `SLACK_FORUM_NOTIFICATION` | Set to `true` to enable Slack notifications for forum thread creation, replies, and open/close status changes (optional) |
| `SLACK_BOT_TOKEN` | Slack Bot Token (`xoxb-…`) with `chat:write` and `chat:write.public` scopes; required when `SLACK_FORUM_NOTIFICATION=true` |
| `SLACK_FORUM_CHANNEL_ID` | Slack channel ID where forum notifications are posted; required when `SLACK_FORUM_NOTIFICATION=true` |

QDash application settings are committed under `config/app`, `config/domain`, and
`config/copilot`; `CONFIG_PATH` is only for the Qubex backend configuration tree.

`AGENT_RUNTIME_ENABLE_WRITE_TOOLS=true` should be used only in a trusted experimental
deployment. The runtime uses its service credential for these calls. Copilot never runs a write
operation itself: when it calls one, the chat shows an approval card with the exact arguments, and
the runtime runs the operation only after the user clicks **Approve**, with the arguments shown. A
decision is accepted only for the approval the latest answer asked for, so it cannot run the same
operation twice.

A chat turn runs until it answers or the user presses Stop; there is no time limit by default,
because a tool waiting on a calibration can legitimately be quiet for an hour. While a turn is
quiet the runtime sends a keepalive every `AGENT_RUNTIME_PING_MS` (default 15 s), forwarded as an
SSE comment, so proxies and tunnels do not drop the idle stream, and the API applies no read
timeout to the runtime stream. Stop in the chat aborts the turn in the runtime through
`POST /copilot/chat/stop`; closing the browser alone does not, and a retry with the same request
recovers the committed answer. Two optional budgets remain for deployments that want them:
`AGENT_RUNTIME_WRAP_UP_MS` tells the model to stop calling tools and answer with what it has after
that long, and `AGENT_RUNTIME_TIMEOUT_MS` aborts the turn outright (both in ms, 0 disables).
`AGENT_RUNTIME_MODEL_STREAM_TIMEOUT_MS` (default 180 s) still limits a single model request.

The Pi Agent Runtime is an opt-in Compose service. When `copilot_backend: pi`, set the following in
`.env` before starting the stack:

```dotenv
COMPOSE_PROFILES=agent-runtime
```

Leave `COMPOSE_PROFILES` unset when using `copilot_backend: litellm`; normal Compose startup then
does not build or create the Agent Runtime container. Multiple profiles use a comma-separated value,
for example `COMPOSE_PROFILES=agent-runtime,tunnel`.

### Default Color Theme

Set `NEXT_PUBLIC_DEFAULT_THEME` in `.env` to choose the initial UI theme:

```dotenv
NEXT_PUBLIC_DEFAULT_THEME=light
```

Supported values are `light`, `dark`, `cupcake`, `emerald`, `corporate`, `synthwave`, `nord`,
`night`, `dracula`, `dim`, `abyss`, `business`, `coffee`, and `sunset`. An unset or unsupported
value falls back to `light`.

A theme selected from **Settings** is saved in the browser and takes precedence over the deployment
default. `NEXT_PUBLIC_DEFAULT_THEME` is embedded in the Next.js application at build time, so rebuild
the UI image after changing it:

```bash
docker compose build ui
docker compose up -d ui
```

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

Complete the Qubex config placement or repository setup before starting services.

## Full Stack

Application file logs use Docker named volumes; use `docker compose logs` to read live service
output. Pi conversation checkpoints use the `agent-runtime-state` named volume. Keep that volume
when recreating containers so interrupted chat and analysis work can resume.

Start all enabled services:

```bash
uv run --env-file .env --isolated --locked --no-dev qdash-updater start
docker compose up -d --build
```

If Go Task is installed, `task deploy-local` performs the same startup and also pulls an optional
external knowledge repository configured by `KNOWLEDGE_REPO_URL`.

Open:

- QDash UI: <http://localhost:5714/login>
- API docs: <http://localhost:5715/docs>
- Prefect: <http://localhost:4200>

## Remote Access

Set `TUNNEL_TOKEN` in `.env` and add `tunnel` to `COMPOSE_PROFILES`. Keep
`agent-runtime` in the comma-separated value when the Pi backend is enabled:

```dotenv
COMPOSE_PROFILES=agent-runtime,tunnel
```

Then run:

```bash
uv run --env-file .env --isolated --locked --no-dev qdash-updater start
docker compose up -d --build
```

This starts the Compose stack with the enabled profiles. `task deploy` is the equivalent Go Task
command; it appends `tunnel` while preserving profiles already configured in `.env`.
