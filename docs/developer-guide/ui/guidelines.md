# UI Development Guidelines

Code under `ui/` follows QDash-specific placement, export, and tooling conventions so routes stay
small and features remain testable.

## Stack

| Tool | Role |
| --- | --- |
| Next.js 16 and React 19 | App Router and component runtime |
| TypeScript 6 | Strict application types |
| Bun 1.4 | Package manager and script runtime |
| TanStack Query | Generated server-state hooks and caching |
| `nuqs` | URL query state |
| Tailwind CSS 4 and DaisyUI 5 | Layout, components, semantic colors, and themes |
| Radix UI | Accessible behavior for dialogs, menus, and tooltips |
| Vitest and Testing Library | Unit and component tests |
| Oxlint, Oxfmt, and Knip | Lint, format, and unused-code checks |

Package versions live in `ui/package.json`; do not duplicate them elsewhere in the codebase.

## Place Files by Responsibility

| Code | Location |
| --- | --- |
| Route entry | `ui/src/app/**/page.tsx` |
| Feature page or component | `ui/src/components/features/<feature>/` |
| Reusable interaction or presentation | `ui/src/components/ui/` |
| Charts | `ui/src/components/charts/` |
| Global navigation and layout | `ui/src/components/layout/` |
| Context provider | `ui/src/contexts/` |
| Reusable hook | `ui/src/hooks/` |
| URL-backed hook | `ui/src/hooks/url-state/` |
| Utility | `ui/src/lib/` or `ui/src/lib/utils/` |
| Manual application type | `ui/src/types/` |
| Generated API code | `ui/src/client/`, `ui/src/schemas/` |

Do not edit generated API code. A route file delegates substantial rendering and state to a
`*PageContent` component.

## Name and Export Modules

Use PascalCase for React component and context files, `use` plus camelCase for hooks, and camelCase
for utilities. Give components a role-specific name such as `EvaluationRequestModal`; avoid names
such as `Modal2` or `Data`.

`page.tsx` and `layout.tsx` use default exports because Next.js requires them. Components, hooks,
contexts, and utilities use named exports. A dynamically imported component can expose both when
the loader requires a default export.

Use established aliases:

- `@/contexts/*` for context;
- `@/hooks/url-state` or `@/hooks/useUrlState` for URL state;
- `@/lib/utils/*` for focused utilities;
- generated hooks from `@/client/<tag>/<tag>` and types from `@/schemas`.

## Keep Boundaries Explicit

- Use generated TanStack Query hooks for API state.
- Use Context only for state shared across unrelated routes or surfaces.
- Use `nuqs` for shareable filters, selections, and date ranges.
- Use React Hook Form and Zod for validated multi-field forms.
- Reuse `Dialog`, `DropdownMenu`, `Tooltip`, `PageHeader`, `PageFiltersBar`, and other existing
  primitives before adding another abstraction.
- Put general visual rules in `globals.css`; keep one-off layout in component classes.

See [Components and State](./components.md) for choosing boundaries and
[UI Architecture](./architecture.md) for the complete data flow.

## Run the Development Loop

From the repository root:

```bash
task dev-local-setup
task dev-local
task test-ui
task ci-ui
task ci-ui-build
```

Use focused commands from `ui/` while iterating:

```bash
bun run test:run src/components/features/tasks/__tests__/TaskWorkbenchRun.test.tsx
bun run lint
bun run fmt:check
bunx tsc --noEmit
```

`task ci-ui` runs tests, Next.js type generation, TypeScript, lint, formatting, Knip, and the Bun
audit. `task ci-ui-build` performs the production build separately.

## Regenerate the API Client

Run `task generate` from the repository root after a backend route or schema changes. Review the
generated OpenAPI and TypeScript diffs, then update feature code and tests to the new contract.

See [API Integration](./api-integration.md) for generated hook usage and invalidation.
