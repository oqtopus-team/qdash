# Developer Commands

Run commands from the repository root unless noted.

## Setup and Services

```bash
task -l                  # list tasks
task dev-local-setup     # install host-side Python/UI dependencies
task dev-local           # Docker services + host API/UI
task dev-local-down      # stop host API/UI and local Docker Compose services
task deploy-local        # full Docker Compose stack
```

## Checks

```bash
task lint                # auto-fix Python and UI lint/format
task ci-lint             # check Python lint/format
task ci-typecheck        # mypy
task test                # all Python tests
task test-api            # API tests
task test-workflow       # workflow tests
task test-ui             # UI tests
task check               # broad local check
```

## Build and Generation

```bash
task generate            # OpenAPI + generated UI client
task build               # UI production build
task build-docs          # documentation build
```

## Secrets

```bash
task scan-leaks
task scan-leaks-staged
task scan-secrets
```
