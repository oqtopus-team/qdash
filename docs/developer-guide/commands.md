# Developer Commands

Run commands from the repository root unless noted.

## Setup and Services

```bash
task -l                  # list tasks
task dev-local-setup     # install host-side Python/UI dependencies
task dev-services        # Docker services with loopback ports for host development
task dev-api-local       # host API on API_PORT (default 5715)
task dev-ui-local        # host UI on UI_INTERNAL_PORT (default 5716)
task dev-proxy-local     # Caddy browser entry point on UI_PORT (default 5714)
task dev-local           # Docker services + host API/UI/Caddy
task dev-local-down      # stop host processes and the compose.host.yaml stack
task deploy-local        # full Docker Compose stack
```

Open the host development stack at `http://localhost:5714`; its API and Prefect destinations are
`/api` and `/prefect`. Use the same Compose file list when managing an override stack.

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
task test-ui             # UI tests
task ci                  # Python lint, type checking, and tests
task check-all           # full local checks including UI and secret scan
```

## Build and Generation

```bash
task generate            # OpenAPI + generated UI client
task generate-task-catalog # workflow task metadata catalog
task build               # UI production build
task build-docs          # documentation build
task check-docs-links    # documentation build, links, and anchors
```

## Secrets

```bash
task scan-leaks
task scan-leaks-staged
task scan-secrets
```
