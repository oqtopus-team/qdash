# Styling

QDash uses Tailwind utilities for layout and DaisyUI components and semantic colors for the visual
system. `ui/src/app/globals.css` contains only project-wide behavior and theme overrides.

## Apply Classes in This Order

1. Start with the DaisyUI component class when one exists, such as `btn`, `card`, `input`, or
   `alert`.
2. Add the applicable DaisyUI modifier for intent or size.
3. Add Tailwind utilities for local layout, spacing, and responsive behavior.
4. Add custom CSS only when the rule must apply across the application or DaisyUI and Tailwind
   cannot express it.

Do not reproduce a component's base styles with a long utility list. Do not add inline styles for
ordinary layout or theme colors.

## Use Semantic Colors

Use `base-*` colors for most surfaces and content. Use `primary` for the main action, and use
`info`, `success`, `warning`, and `error` for their semantic states. Pair a filled semantic
background with its matching `*-content` foreground.

Avoid fixed Tailwind colors for text and surfaces because they do not adapt to all QDash themes.
A fixed color is acceptable for plots or data encodings whose meaning must not change with the
theme.

Do not add `dark:` variants for DaisyUI semantic colors. Their values already change with
`data-theme`.

## Keep Theme Sources Synchronized

Theme names live in `ui/src/constants/themes.ts`. Their DaisyUI theme files and the QDash light and
dark overrides live in `ui/src/app/globals.css`. `ThemeContext.tsx` applies the selected name to
the document's `data-theme` attribute.

When adding a theme:

1. Import its DaisyUI theme file in `globals.css`.
2. Add its name to `AVAILABLE_THEMES`.
3. Add it to `DARK_THEMES` when it needs dark-mode logo and surface treatment.
4. Check representative pages, dialogs, charts, status colors, and focus indicators.

## Size Selectors from Their Container

Selectors fill their parent. The containing filter item owns the width, while `useSelectStyles`
owns theme integration.

- Give desktop filter containers a fixed `sm:w-*` width; mobile retains the full-width default.
- Wrap a selector next to a button in `min-w-0 flex-1` so the button remains visible.
- Let long selected labels truncate while the option menu remains wide enough to read.

## Limit Global CSS

`globals.css` defines the shared card, button, form, feedback, motion, and theme behavior. Before
adding a global selector, confirm that every matching component should change.

Avoid `transition-all` on repeated data rows or grid cells. The global stylesheet limits motion
to interactive properties and disables meaningful animation when the user prefers reduced motion.

## Verify a Styling Change

Check at least the light and dark QDash themes, keyboard focus, disabled states, narrow layouts,
and any dense grid or table affected by the change. Run `task ci-ui-build` to catch invalid class
generation and production-only rendering failures.

See [UI Design Policy](./design-policy.md) for visual decisions and acceptable exceptions.
