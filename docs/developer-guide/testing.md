# Testing

Run the checks for the area you changed, then the full check before every push.

| Changed area | Command | Details |
| --- | --- | --- |
| API | `task test-api` | [API tests](./api/testing.md) |
| Workflow | `task test-workflow` | [Workflow tests](./workflow/testing.md) |
| UI | `task test-ui` | [UI tests](./ui/testing.md) |
| Python client / SDK | `task test-client` / `task test-sdk` | [Client](../reference/clients/python.md) |
| TypeScript client / SDK | `task test-client-ts` / `task test-sdk-ts` | [Client](../reference/clients/typescript.md) |
| Pi extensions | `task ci-pi-packages` | [Packages](./agent/packages.md) |
| Agent runtime | `task ci-agent-runtime` | [Architecture](./agent/architecture.md) |
| Docs | `task build-docs`, `task check-docs-links` | [Writing guidelines](./docs-guidelines.md) |

For a focused Python test, use `uv run pytest path/to/test_file.py -v`.
API contract changes also require `task generate` and tests for affected clients.
Mermaid changes require `task check-docs-mermaid`.

Before pushing, follow [Development Flow](./development-flow.md#before-pushing):
run `nix develop -c task check` on the host, or `task check` in the DevContainer.
