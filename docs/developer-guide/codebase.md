# Codebase Map

QDash has four main code areas.

| Area | Path | Notes |
| --- | --- | --- |
| UI | `ui/` | Next.js, React, TypeScript, DaisyUI, TanStack Query |
| API | `src/qdash/api/` | FastAPI routers, services, schemas, middleware |
| Workflow | `src/qdash/workflow/` | Prefect flows, deployment service, user flow worker, scheduler, task execution |
| Shared model/repository code | `src/qdash/common/`, `src/qdash/datamodel/`, `src/qdash/dbmodel/`, `src/qdash/repository/` | Shared config, document models, repositories |

## Generated Files

Do not manually edit:

- `ui/src/client/`
- `ui/src/schemas/`
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
- `CONFIG_PATH` ↔ `/app/config/qubex-config`
- `CALTASKS_PATH` ↔ `/app/qdash/workflow/calibtasks`
