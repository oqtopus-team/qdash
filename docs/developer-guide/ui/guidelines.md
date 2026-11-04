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

A preview of one task result, opened from a Task Results row or an Execution Flow node, is
`TaskResultPreviewSidebar` in `ui/src/components/features/task-results/`. It fetches the result
from the task id and links to the full page, so a page holds only the selected id and does not
build a result panel of its own.

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

The typeface is Geist Sans, with Geist Mono for identifiers and numbers (`font-mono`). Both are
self-hosted from the `geist` package: `ui/src/app/layout.tsx` loads them through `next/font` and
exposes `--font-geist-sans` and `--font-geist-mono`; the `@theme` block in `globals.css` maps them
to Tailwind's `--font-sans` and `--font-mono`, so no page needs a `font-sans` class. Libraries that
bypass the cascade (Monaco, Plotly) take `sansFontFamily` and `monoFontFamily` from
`ui/src/lib/fonts.ts`; do not write a font stack anywhere else.

| Role | Classes |
| --- | --- |
| Page title (`h1`, `PageHeader`) | `text-xl font-medium` |
| Section, card, dialog, and item title (`h2`, `h3`, `card-title`, `DialogTitle`) | `text-sm font-medium` |
| Body, labels, buttons, table cells | `text-sm` |
| Supporting text, timestamps, badges | `text-xs text-base-content/60` |
| Sub-section label inside a card, table header, sidebar section | `text-xs font-medium text-base-content/60`, sentence case |
| Numeral in a stat tile | `stat-value` |

`font-medium` is the only emphasis; do not use `font-semibold` or `font-bold`. Do not use
`text-base`, `text-lg`, `text-2xl` and above, arbitrary sizes such as `text-[11px]`, or responsive
size variants such as `sm:text-lg`; pick one size for every viewport. When primary and secondary
text share a line, separate them with color, not size.
Labels are sentence case; no `uppercase` or `tracking-*` on interface text.

`globals.css` applies the same scale to DaisyUI: `.btn`, `.badge`, `.card-title`, `.table th`, and
`.stat-value` use weight 500, and `.stat-value` is the one step above the page title (1.5rem,
tabular numerals). `ui/src/lib/react-select-theme.ts` and
`ui/src/components/features/cryo/blocknote-theme.css` follow the same values.

Exceptions: the error and not-found pages, the sign-in hero title, Monaco editor font settings,
and chip, coupling, and topology grid cells whose text scales with the cell size.

## Write Interface Copy

A page title is the navigation label (`Metrics`, not `Chip Metrics Dashboard`); the description
under it is one line of what the page shows, without a trailing period. Headings, labels, buttons
and placeholders end without a period and never carry an exclamation mark. Empty states name the
context, not the visitor: `Ask about calibration data`, not `Good evening, Alice`. Placeholders
are short (`Ask a question`, `Search tasks`).

## Keep Surfaces Flat

Depth comes from borders and spacing, not from gradients, glow, or motion. `globals.css` sets the
DaisyUI components once; feature code does not add decoration on top.

| Surface | Rule |
| --- | --- |
| Button | Solid DaisyUI fill, `0.5rem` radius, no shadow, no hover lift |
| Card, table, alert, dropdown | 1px border in `base-content/10`, hairline shadow, `0.5rem` to `0.75rem` radius |
| Input | 1px border, primary border plus a 3px soft ring on focus |
| Active navigation or tab | Tinted background (`primary` at 12%) with primary text, not a filled gradient |
| Floating layer (modal, drawer, menu) | One soft shadow; this is the only place `shadow-md` or larger belongs |
| Transitions | `transition-colors` or `transition-transform`; `transition-all` only where a width or height must animate |
| Motion | No `animate-ping`, no `hover:scale`, no pulsing status dots; `animate-pulse` only on skeletons and `animate-spin` only on loaders |

Color means status. `success`, `warning`, `error`, and `info` mark state; `primary` marks the one
action or selection on screen. A number in a stat tile is neutral unless it reports a state, and
decorative uses of `secondary` and `accent` are avoided.

A qubit or coupling id is always a `QubitTile` (`ui/src/components/ui/QubitTile.tsx`): a mono id in a
small square-cornered box, the same shape as a cell of the chip grid, with a status dot when the
reference carries a status. Do not render ids as plain badges.

Icons come from `lucide-react`, 16px to 18px, in the color of their text role (`text-base-content/60`
for meta), never in `secondary` or `accent`. Product UI does not use emoji or emoji images; `EmptyState` renders
a lucide icon from its `emoji` name map, and toasts use lucide status icons. `FluentEmoji` remains
only for user-chosen avatars and the sign-in page.

## Draw Charts from One Theme

Every Plotly chart renders through `Plot` in `ui/src/components/charts/Plot.tsx`, which merges
`themedLayout` from `ui/src/lib/chartTheme.ts` under the caller's layout: transparent backgrounds,
a hairline grid, muted ticks and legend, the interface font and a shared `colorway`. A chart file
therefore sets only what is specific to it (titles, ranges, margins, axis types) and never
`plot_bgcolor`, `paper_bgcolor`, `gridcolor` or legend backgrounds. A fetched figure that paints
its own `paper_bgcolor` keeps its own text, grid and series colors, because the theme cannot know
which text reads on that background; it receives only the font family.

Series colors come from `chartTheme(useIsDarkTheme())`: `accent` for the one series that matters,
`secondary` for a right-hand axis, `seriesColor(theme, i)` for the i-th of several, and `pass` /
`fail` / `warn` only when a color means a threshold result. Do not write hex colors in chart
code; the palette has a light and a dark variant and the hook keeps charts readable on every theme.

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
