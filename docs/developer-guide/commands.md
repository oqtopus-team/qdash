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
task test-client         # Python client tests
task test-client-ts      # TypeScript client checks
task ci-pi-packages      # pi extension and release-script checks
task ci-agent-runtime    # runtime tests and typecheck
task test-ui             # UI tests
task ci                  # Python lint, type checking, and tests
task check               # required before every push; Python, UI, workspace packages, secret scan
                         # task check-all is an alias
```

## Build and Generation

```bash
task generate            # OpenAPI + generated UI client
task generate-task-catalog # workflow task metadata catalog
task build               # UI production build
task build-client-ts     # build the local TypeScript client for pi CLI development
task build-docs          # documentation build
task check-docs-links    # documentation build, links, and anchors
```

## Secrets

```bash
task scan-leaks
task scan-leaks-staged
task scan-secrets
```
