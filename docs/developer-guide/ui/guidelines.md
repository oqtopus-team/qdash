# UI Development Guidelines

Code under `ui/` follows QDash-specific placement, export, and tooling conventions so routes stay
small and features remain testable.

## Stack

| Tool | Role |
| --- | --- |
| Next.js and React | App Router and component runtime |
| TypeScript | Strict application types |
| Bun | Package manager and script runtime |
| TanStack Query | Generated server-state hooks and caching |
| `nuqs` | URL query state |
| Tailwind CSS and DaisyUI | Layout, components, semantic colors, and themes |
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

Choose the narrowest owner that preserves the required behavior:

| State | Owner |
| --- | --- |
| API records and mutation status | Generated TanStack Query hook |
| Shareable filters, selections, and date ranges | Existing `use*UrlState` hook |
| Authentication, active project, theme, or global layout | Existing context |
| One component subtree | Local state or a focused hook |
| Validated multi-field form | React Hook Form with Zod |

Do not copy query results into Context or synchronize duplicate response state by hand. Invalidate
the affected generated query keys after a mutation.

Keep feature-specific composition in `components/features/`. Move a component to
`components/ui/` only when its API no longer depends on a feature model and at least two callers
can reuse it. Search the existing primitives before adding one; QDash already provides dialogs,
menus, tooltips, page framing, tables, loading and empty states, errors, confirmation, and toast
feedback.

Use DaisyUI for buttons, cards, inputs, badges, tables, alerts, and other visual components. Reuse
the shared Radix-based `Dialog`, `DropdownMenu`, and `Tooltip` wrappers when focus management,
keyboard navigation, portals, dismissal, or collision handling requires them. Feature code does
not import another headless primitive to replace an established wrapper.

How these boundaries connect: [UI Architecture](./architecture.md).

## Set Type with Three Sizes and Two Weights

Text uses three sizes and two weights. Hierarchy comes from spacing and color, not from a larger
or bolder font. `body` in `ui/src/app/globals.css` sets 14px, so unsized text is body text.

| Role | Classes |
| --- | --- |
| Page title (`h1`, `PageHeader`) | `text-xl font-medium` |
| Section, card, dialog, and item title (`h2`, `h3`, `card-title`, `DialogTitle`) | `text-sm font-medium` |
| Body, labels, buttons, table cells | `text-sm` |
| Supporting text, timestamps, badges | `text-xs text-base-content/60` |
| Sub-section label inside a card | `text-xs font-medium uppercase tracking-wide text-base-content/60` |
| Numeral in a stat tile | `stat-value` |

`font-medium` is the only emphasis; do not use `font-semibold` or `font-bold`. Do not use
`text-base`, `text-lg`, `text-2xl` and above, arbitrary sizes such as `text-[11px]`, or responsive
size variants such as `sm:text-lg`; pick one size for every viewport. When primary and secondary
text share a line, separate them with color, not size.

`globals.css` applies the same scale to DaisyUI: `.btn`, `.badge`, `.card-title`, `.table th`, and
`.stat-value` use weight 500, and `.stat-value` is the one step above the page title (1.5rem,
tabular numerals). `ui/src/lib/react-select-theme.ts` and
`ui/src/components/features/cryo/blocknote-theme.css` follow the same values.

Exceptions: the error and not-found pages, the sign-in hero title, Monaco editor font settings,
and chip, coupling, and topology grid cells whose text scales with the cell size.

## Write TypeScript

`ui/tsconfig.json` enables strict checking, unused-symbol checks, fallthrough checks, and
`noEmit`. Model finite UI states with string or discriminated unions instead of independent
booleans that allow impossible combinations.

Import API request and response types from `@/schemas`; do not copy generated interfaces into a
feature. Use `unknown` and narrow it at an untyped boundary instead of spreading `any` through
props or state. Keep unavoidable assertions at the deserialization, DOM, or third-party library
boundary, and render reachable missing states instead of hiding them with a non-null assertion.

Generated hooks already type their data, errors, variables, and callbacks. Add explicit types
when data crosses a generic boundary, not to repeat inference that is already precise.

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
