# Codebase Map

QDash keeps application code and generated clients in the following areas.

| Area | Path | Notes |
| --- | --- | --- |
| UI | `ui/` | Next.js, React, TypeScript, DaisyUI, TanStack Query |
| API | `src/qdash/api/` | FastAPI routers, services, schemas, middleware |
| Workflow | `src/qdash/workflow/` | Prefect flows, deployment service, user flow worker, scheduler, task execution |
| Shared model/repository code | `src/qdash/common/`, `src/qdash/datamodel/`, `src/qdash/dbmodel/`, `src/qdash/repository/` | Shared config, document models, repositories |
| Python client | `clients/python/` | Typed client package and service wrappers |
| TypeScript client | `clients/typescript/` | Published client; local workspace dependency of pi-qdash |
| Agent runtime | `agent-runtime/` | Copilot sessions and host integration for pi tools |
| Pi extensions | `packages/pi-qdash/`, `packages/pi-qcaleval/` | Independently published tools and skills |

The runtime, TypeScript client, and pi extensions share the root Bun workspace and
`bun.lock`. The UI and docs keep separate installs. See [Pi Packages](./copilot/packages.md)
for setup and [Pi Extension Design](./copilot/extensions.md) for extension boundaries.

## Generated Files

Do not manually edit:

- `ui/src/client/`
- `ui/src/schemas/`
- `clients/typescript/src/generated/`
- `docs/oas/openapi.json`

When API schemas or routes change, run:

```bash
task generate
```

## Runtime Paths

Host-side development and Docker containers see different absolute paths. Use the shared runtime
path helpers in `src/qdash/common/config/path_resolver.py` instead of adding local path fallbacks
inside individual services.

Important mounted paths:

- `CALIB_DATA_PATH` ↔ `/app/calib_data`
- `CONFIG_PATH` ↔ `/app/config/qubex-config` for the Qubex backend configuration repository/data
- `CALIB_TASKS_PATH` ↔ `/app/qdash/workflow/calibtasks`

QDash application configuration is separate from `CONFIG_PATH` and lives under `config/app`,
`config/domain`, and `config/copilot`.
