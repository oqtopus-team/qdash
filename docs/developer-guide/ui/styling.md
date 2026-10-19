# Styling

How to apply Tailwind and DaisyUI in QDash components. The design system itself (colors, icons, component classes, animations) is specified in [design-policy.md](./design-policy.md).

## Tailwind CSS Classes

Use Tailwind CSS utility classes for styling:

```tsx
// Good - Tailwind utilities
<div className="flex items-center gap-4 p-4 bg-base-200 rounded-lg">
  <h2 className="text-xl font-bold text-primary">Title</h2>
  <p className="text-sm text-base-content/70">Description</p>
</div>

// Bad - Inline styles
<div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
  <h2 style={{ fontSize: "1.25rem", fontWeight: "bold" }}>Title</h2>
</div>
```

## Selector Width

Selectors (`components/selectors/`) fill 100% of their parent. The container decides the width; `useSelectStyles` returns theme styles only and does not compute widths.

```tsx
// Good - container sets a fixed width
<PageFiltersBar.Item className="sm:w-64">
  <ChipSelector selectedChip={chip} onChipSelect={setChip} />
</PageFiltersBar.Item>

// Bad - no width on a shrink-to-fit container (selector collapses to placeholder width)
<PageFiltersBar.Item>
  <ChipSelector selectedChip={chip} onChipSelect={setChip} />
</PageFiltersBar.Item>
```

- Use a fixed `sm:w-*`, not `sm:min-w-*`, so the control width stays constant across selections. Mobile keeps the `w-full` default from `PageFiltersBar.Item`.
- When a selector shares a row with a button (for example a clear button), wrap it in `min-w-0 flex-1` so it shrinks instead of pushing the button out.
- Long labels ellipsize inside the control; the dropdown menu grows to `max-content` so the full option text stays readable.

## DaisyUI Components

Use DaisyUI component classes (`btn`, `card`, `input`, `select`, `table`, `badge`) for consistent UI. The class reference with examples is in [design-policy.md](./design-policy.md#daisyui-component-classes).

## Theme Support

QDash supports 35+ DaisyUI themes. Users can switch themes in Settings (`/settings`).

```tsx
// Use semantic color classes (auto-adjust to theme)
<div className="bg-base-100 text-base-content">
  <span className="text-primary">Primary color</span>
  <span className="text-secondary">Secondary color</span>
  <span className="text-accent">Accent color</span>
</div>

// Avoid hardcoded colors
// Bad
<div className="bg-white text-black">...</div>

// Good
<div className="bg-base-100 text-base-content">...</div>
```

The full semantic palette and opacity modifiers: [design-policy.md](./design-policy.md#color-system).

### Adding New Themes

1. Add the import to `globals.css`: `@import "daisyui/theme/themename.css";`
2. Add the theme name to the `themes` array in `/ui/src/app/(auth)/settings/page.tsx`

## Rich Interactive Design System

QDash enhances DaisyUI with a custom **Rich Interactive Design System** defined in `globals.css`: cards, buttons, inputs, badges, dropdowns, tables, and scrollbars get hover, focus, shadow, and gradient treatment without extra classes. The element-by-element table and the `card-hover` / `card-interactive` / `card-glass` utilities are in [design-policy.md](./design-policy.md#rich-interactive-design-system).

### Performance Guidelines

Transitions are **only applied to interactive elements** to prevent animation jank on data-heavy pages:

```tsx
// Good - globals.css handles card transitions
<div className="card">Content</div>

// Good - Custom transition overrides globals.css
<div className="card transition-all duration-200 hover:scale-105">Content</div>

// Bad - Avoid transition-all on many items (causes jank)
{items.map((item) => (
  <div className="transition-all duration-300">{item}</div>
))}

// Good - Use transition: none for data-heavy views
<table className="table">
  <tbody>
    {/* Table rows have transition: none by default */}
  </tbody>
</table>
```

**Key rules:**

1. Don't add `transition-*` classes to elements that globals.css already styles (cards, buttons, badges)
2. Use `transition: none` for elements in lists/grids with many items
3. Avoid `transition-all` - prefer specific properties like `transition-shadow`
4. The system respects `prefers-reduced-motion` automatically

The animation utility classes (`page-transition`, `stagger-item`, `status-pulse`) are listed in [design-policy.md](./design-policy.md#animation-transitions).
