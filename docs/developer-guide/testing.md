# Developer Testing

Prefer focused tests for the code you changed. Broaden only when changing shared behavior,
runtime paths, API contracts, generated clients, or UI routing.

## Python

```bash
task test-fast
task test-api
task test-workflow
uv run pytest path/to/test_file.py -v
```

## UI

```bash
task test-ui
cd ui && bunx tsc --noEmit
cd ui && bun run lint
cd ui && bun run fmt:check
```

## API Contract Changes

If backend route schemas or generated clients change:

```bash
task generate
task test-api
task test-ui
```

## Workflow Changes

For workflow engine, scheduler, deployment service, or task execution changes:

```bash
task test-workflow
uv run pytest tests/qdash/workflow/engine -v
```
