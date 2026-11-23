# UI Development Guidelines

Use the shared components and styling rules so new features fit the rest of QDash.

## Place Files by Responsibility

Keep routes thin and rendering in named `*PageContent` components. Use the locations in
[UI Architecture](./architecture.md#responsibility-boundaries); never edit generated clients or
schemas. Reuse `TaskResultPreviewSidebar` for result previews.

## Name and Export Modules

Use PascalCase for components and contexts, `useCamelCase` for hooks, and camelCase for utilities.
Ordinary modules use named exports; `page.tsx` and `layout.tsx` use default exports.
Use established aliases: `@/contexts`, `@/hooks/url-state`, `@/lib/utils`, `@/client`, and `@/schemas`.

## Keep Boundaries Explicit

Follow [state ownership](./architecture.md#state-ownership). DaisyUI provides visual components;
shared Radix wrappers provide focus, dismissal, portals, and keyboard behavior. Reuse the root
`TooltipProvider`. Navigation links need clear labels, not tooltips repeating their destinations.
Chat links alone use `LinkHoverCardProvider`; external links are described without fetching them.
Inline autocomplete keeps focus in its text field and uses combobox/listbox semantics.

## Set Type with Three Sizes and Two Weights

| Role | Classes |
| --- | --- |
| Page title | `text-xl font-medium` |
| Section, card, dialog title | `text-sm font-medium` |
| Body, labels, controls | `text-sm` |
| Supporting text | `text-xs text-base-content/60` |
| Stat numeral | `stat-value` |

Use sentence case, regular or medium weight, and no arbitrary or responsive text sizes.
Geist fonts come from `ui/src/app/layout.tsx`; libraries needing explicit fonts use
`ui/src/lib/fonts.ts`. Editors, error pages, sign-in heroes, and scalable topology cells have
special sizing needs.

## Write Interface Copy

Use the navigation label as the page title. Keep descriptions to one line. Labels, buttons,
headings, and placeholders omit final periods and exclamation marks.

## Keep Surfaces Flat

Use borders and spacing, not gradients, glow, hover lifts, or decorative animation.
Theme tokens own corner radii: `--radius-field` for controls and `--radius-box` for panels.
Do not override button radii or use obsolete DaisyUI 4 color variables.
Use semantic status colors and reserve primary emphasis for an action or selection.
Render target IDs with `QubitTile` and icons with Lucide, not emoji.

## Space Icon Buttons Optically

A labeled `.btn` marks its direct-child icon or replacement spinner with
`data-icon="inline-start"` or `data-icon="inline-end"`. The shared CSS owns icon size, gap, and
optical padding; do not add competing size or gap utilities. Icon-only buttons use
`btn-square` or `btn-circle`, an accessible name, and no `data-icon` hook.
Start-aligned rows and conditionally rendered labels follow the existing spacing exceptions.

## Label Checkboxes and Radios with the Whole Row

Put a labeled checkbox, radio, or toggle directly inside a `choice-field` label. Checkboxes and
radios precede their text; radio groups share a name. Do not combine `choice-field` with DaisyUI's
`label` class or add vertical margins to the control. Unlabeled controls need `aria-label`.

## Size Controls That Share a Row

Use matching DaisyUI size steps for inputs, selects, and buttons; do not force their height.
React-Select uses `useSelectStyles` or `getDaisySelectStyles`, without call-site height overrides.

## Draw Charts from One Theme

Use `ui/src/components/charts/Plot.tsx` and `ui/src/lib/chartTheme.ts`. Set chart-specific axes,
ranges, and titles, not duplicate background, grid, or legend colors. Use the shared series
palette with `useIsDarkTheme()`; fetched figures with their own background retain their colors.

## Write TypeScript

Use strict types and discriminated unions for finite states. Import API types from `@/schemas`.
Narrow `unknown` at external boundaries; avoid `any`, blanket assertions, and duplicate interfaces.

## Run the Development Loop

Use Bun in `ui/`. Start with `task dev-local-setup` and `task dev-local` from the repository root.
Follow [UI Testing](./testing.md) for checks.

## Regenerate the API Client

Run `task generate` after contract changes and review the generated diff.
[API Integration](./api-integration.md) covers hooks and invalidation.
