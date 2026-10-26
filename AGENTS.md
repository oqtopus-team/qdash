# QDash Agent Guide

This file is the Codex-facing project guide. Keep it concise and update it when repository-wide conventions change. The older `CLAUDE.md` is retained as a Claude Code reference, but Codex should use this file first.

## Project Overview

QDash is a web platform for managing and monitoring qubit calibration workflows.

- Repository: `oqtopus-team/qdash`
- License: Apache 2.0
- Public docs: <https://oqtopus-team.github.io/qdash/>

## Architecture

- Frontend: `ui/` uses Next.js, React, TypeScript, DaisyUI, TanStack Query, and Bun.
- Backend API: `src/qdash/api/` uses FastAPI with MongoDB/PostgreSQL-related services.
- Workflow engine: `src/qdash/workflow/` uses Prefect 3 and qubex.
- Shared data/model code lives under `src/qdash/common`, `src/qdash/datamodel`, `src/qdash/dbmodel`, and repository/service modules.

Read `docs/developer-guide/architecture.md` and the more specific docs under `docs/developer-guide/` before making broad changes.

## High-Value References

- Setup: `docs/developer-guide/setup.md`
- Development flow and commits: `docs/developer-guide/development-flow.md`
- API design: `docs/developer-guide/api/design.md`
- API testing: `docs/developer-guide/api/testing.md`
- UI guidelines: `docs/developer-guide/ui/guidelines.md`
- UI architecture: `docs/developer-guide/ui/architecture.md`
- UI testing: `docs/developer-guide/ui/testing.md`
- UI design policy: `docs/developer-guide/ui/design-policy.md`
- Workflow quickstart: `docs/developer-guide/workflow/quickstart.md`
- Workflow architecture: `docs/developer-guide/workflow/engine-architecture.md`
- Workflow testing: `docs/developer-guide/workflow/testing.md`
- Documentation guidelines: `docs/developer-guide/docs-guidelines.md`
- Database collections: `docs/reference/database-structure.md`

## Generated Code

Do not manually edit generated files:

- `ui/src/client/`
- `ui/src/schemas/`
- `clients/typescript/src/generated/`
- `docs/oas/openapi.json`

When backend API schemas or routes change, run `task generate` from the repository root to regenerate the OpenAPI document and TypeScript clients.

## Common Commands

Run commands from the repository root unless a directory is specified.

- Show available tasks: `task -l`
- Install host-side local dependencies: `task dev-local-setup`
- Start lightweight host-side stack: `task dev-local`
- Start full Docker Compose stack: `task deploy-local`
- Start API only: `uvicorn src.qdash.api.main:app --reload`
- Start UI dev server: `task dev-ui` or `bun run dev` in `ui/`
- Generate API client: `task generate`
- Python tests: `task test`
- Fast Python test loop: `task test-fast`
- API tests: `task test-api`
- Workflow tests: `task test-workflow`
- UI tests: `task test-ui`
- TypeScript client checks: `task test-client-ts`
- Agent runtime tests and typecheck: `task ci-agent-runtime`
- Python CI checks: `task ci`
- Required before every push: `task check` (`task check-all` is an alias)
- Python lint/format with fixes: `task lint-python`
- UI lint/format with fixes: `task lint-ui`
- UI production build: `task build` or `task ci-ui-build`
- Docs dev server: `task docs`
- Docs build: `task build-docs`

Use focused tests during development. Before every push, run the full `task check`
regardless of change size, including documentation-only changes.

## Python Conventions

- Python supports `>=3.11,<3.13`.
- Use `uv run ...` for Python tooling when invoking commands directly.
- Ruff line length is 100. The project uses Ruff for linting and formatting.
- Mypy is strict for application code. Keep types explicit when adding public helpers or cross-module interfaces.
- Tests use pytest. Many tests are designed to run in memory without MongoDB.
- Avoid changing `tools`, `scripts`, or generated requirement exports unless the task is specifically about those areas.

## UI Conventions

- Use Bun in `ui/`.
- `ui/src/app/` should contain routing-only App Router files. Keep `page.tsx` files thin and delegate substantial UI to `*PageContent` components.
- Use named exports for ordinary components, hooks, utilities, and contexts. `page.tsx` and `layout.tsx` use default exports.
- Use imports from established aliases and locations, especially `@/contexts/*`, `@/hooks/useUrlState` or `@/hooks/url-state`, and `@/lib/utils/*`.
- Keep reusable primitives in `ui/src/components/ui/`, feature UI in `ui/src/components/features/`, charts in `ui/src/components/charts/`, and layout in `ui/src/components/layout/`.
- Keep DaisyUI as the visual and theme foundation. Use the established Radix-based primitives in `ui/src/components/ui/` for interactions that need robust focus management, keyboard navigation, portals, dismissal, or collision-aware positioning.
- Do not treat Radix as a wholesale DaisyUI replacement. Prefer DaisyUI for buttons, cards, inputs, badges, tables, and semantic colors; add a headless primitive only when the interaction behavior requires it.
- Use TanStack Query for server state and `nuqs` for URL query state when matching existing patterns.
- Use Lucide React icons where an icon is appropriate.
- Follow `docs/developer-guide/ui/guidelines.md` and `docs/developer-guide/ui/design-policy.md` for implementation and visual design details.

## Documentation Conventions

- Follow `docs/developer-guide/docs-guidelines.md` and use the `technical-docs` skill (`.agents/skills/technical-docs/SKILL.md`) to write, verify and review a page.
- Use the `document-changes` skill (`.agents/skills/document-changes/SKILL.md`) to audit a branch, pull request, commit, or working-tree diff for documentation impact before making documentation fixes.
- Start docs with a direct context sentence.
- Do not add manual tables of contents, summary sections, empty checklists, future-enhancement sections, or emoji.
- Link relevant docs inline instead of adding broad related-document lists.
- Do not restructure `docs/task-knowledge/`; those files have a fixed template consumed by the copilot system.

## Git And PR Conventions

- Use Conventional Commits style: `<type>(<scope>): <summary>`.
- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `ci`, `chore`.
- Scopes: use `api`, `workflow`, `ui`, `docs`, `infra`, or `repo` when clear.
- Keep commit titles short, specific, English, no emoji, and no trailing period.
- For PR text, follow `.github/pull_request_template.md` and `.github/instructions/pull-request-description-instructions.md`.
- Branches usually start from `develop`; common prefixes are `feature/`, `bugfix/`, and `hotfix/`.
- Before every push, including updates to an existing PR, run `task check` from the
  repository root and require exit status 0. Focused tests, pre-commit hooks, and CI
  do not replace this gate. Follow the [pre-push procedure](docs/developer-guide/development-flow.md#before-pushing).
- Stage intended new files before checking so the leak scan includes them. Fetch the
  PR target and use `LEAKS_BASE=origin/<target>` when it is not `develop`.
- Review any auto-fix changes from `task check` and include intended fixes in the
  commit. If you edit files afterward, rerun `task check` before pushing.
- If the check fails or cannot run, resolve the failure before pushing. If blocked,
  report the failed command and reason; do not push or claim validation succeeded.
- Record the command and result in the PR description and final handoff.

## Agent Working Rules

- Check `git status --short` before editing and do not revert unrelated user changes.
- Prefer existing project patterns and local helper APIs over new abstractions.
- Keep edits scoped to the requested area.
- If changing API contracts, update tests and regenerate the client.
- If changing UI behavior, add or adjust Vitest tests where practical and run the relevant UI checks.
- If changing workflow or repository behavior, run the matching Python tests.
- Mention any verification that could not be run and why.
