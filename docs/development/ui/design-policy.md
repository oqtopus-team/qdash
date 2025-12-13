# UI Design Policy for QDash

This document defines the visual design conventions and standards for the QDash project. All contributors should follow these guidelines when creating new UI components or features.

## Table of Contents

1. [Icon System](#icon-system)
2. [Emoji & Illustrations](#emoji--illustrations)
3. [Color System](#color-system)
4. [Component Design](#component-design)
5. [Empty States](#empty-states)
6. [Loading States](#loading-states)
7. [Feedback & Notifications](#feedback--notifications)
8. [Animation & Transitions](#animation--transitions)
9. [Accessibility](#accessibility)
10. [Acceptable Exceptions](#acceptable-exceptions)
11. [Quick Reference](#quick-reference)

---

## Icon System

### Use Lucide React

QDash uses **Lucide React** as the official icon library. This provides a consistent, modern icon set.

```bash
# Already installed
bun add lucide-react
```

### Usage Guidelines

```tsx
// ✅ Good - Import specific icons
import { Settings, ChevronRight, Clock } from "lucide-react";

// Use consistent sizing
<Settings size={18} />        // Navigation, inline icons
<Settings size={20} />        // Buttons, actions
<Settings size={24} />        // Headers, emphasis

// ❌ Bad - Don't use other icon libraries
import { FaSettings } from "react-icons/fa";  // Don't use react-icons
import { Icon } from "@iconify/react";         // Don't use iconify
```

### Icon Sizing Standards

| Context            | Size | Example                        |
| ------------------ | ---- | ------------------------------ |
| Sidebar navigation | 18px | `<Cpu size={18} />`            |
| Buttons            | 20px | `<Plus size={20} />`           |
| Page headers       | 24px | `<Settings size={24} />`       |
| Empty states       | 48px | `<FolderOpen size={48} />`     |
| Status indicators  | 16px | `<CheckCircle size={16} />`    |

### Common Icons by Use Case

| Use Case         | Icon                        | Import                              |
| ---------------- | --------------------------- | ----------------------------------- |
| Navigation       | `LayoutGrid`, `List`        | `lucide-react`                      |
| Actions          | `Plus`, `Edit`, `Trash2`    | `lucide-react`                      |
| Status (success) | `CheckCircle`, `Check`      | `lucide-react`                      |
| Status (error)   | `XCircle`, `AlertCircle`    | `lucide-react`                      |
| Status (warning) | `AlertTriangle`             | `lucide-react`                      |
| Status (info)    | `Info`                      | `lucide-react`                      |
| Loading          | `Loader2` (with animation)  | `lucide-react`                      |
| External link    | `ExternalLink`              | `lucide-react`                      |
| Back navigation  | `ArrowLeft`, `ChevronLeft`  | `lucide-react`                      |
| Time/Date        | `Clock`, `Calendar`         | `lucide-react`                      |
| Settings         | `Settings`, `Sliders`       | `lucide-react`                      |
| Download/Export  | `Download`, `FileDown`      | `lucide-react`                      |

---

## Emoji & Illustrations

### Use Microsoft Fluent Emoji

For rich, engaging illustrations (empty states, avatars, decorative elements), use **Microsoft Fluent Emoji** via the `FluentEmoji` component.

```tsx
import { FluentEmoji } from "@/components/ui/FluentEmoji";

// Basic usage
<FluentEmoji name="rocket" size={64} />
<FluentEmoji name="success" size={24} />
<FluentEmoji name="warning" size={20} />
```

### When to Use Fluent Emoji vs Lucide Icons

| Context              | Use                | Example                              |
| -------------------- | ------------------ | ------------------------------------ |
| Interactive elements | Lucide icons       | Buttons, navigation, form controls   |
| Empty states         | Fluent Emoji       | "No results found" illustrations     |
| Toast notifications  | Fluent Emoji       | Success/error feedback               |
| User avatars         | Fluent Emoji       | Profile representations              |
| Decorative accents   | Fluent Emoji       | Page headers, welcome screens        |
| Status badges        | Lucide icons       | Small inline status indicators       |

### Available Emoji Names

```tsx
// Status
"check", "success", "error", "cross", "warning", "info"

// Actions & UI
"prohibited", "no-entry", "sparkles", "party", "lightbulb", "rocket", "fire"

// Data & Charts
"chart", "chart-up", "chart-down"

// Objects
"gear", "wrench", "magnifying-glass", "folder", "file"

// Science & Tech
"atom", "test-tube", "dna"

// Time
"clock", "hourglass"

// Empty states
"empty"

// Avatars (animals, nature, objects)
"fox", "cat", "dog", "rabbit", "bear", "panda", "koala", "tiger", "lion",
"unicorn", "owl", "octopus", "butterfly", "dolphin", "whale", "penguin",
"sun", "moon", "star", "rainbow", "cloud", "snowflake", "cherry", "tulip",
"sunflower", "mushroom", "crystal", "planet"
```

### User Avatars

For consistent user avatars, use the `getAvatarEmoji` function:

```tsx
import { FluentEmoji, getAvatarEmoji } from "@/components/ui/FluentEmoji";

// Generates consistent emoji based on username
const avatarEmoji = getAvatarEmoji(user.username);
<FluentEmoji name={avatarEmoji} size={28} />
```

---

## Color System

### Use Semantic Colors

QDash uses DaisyUI's semantic color system. **Never use hardcoded colors**.

```tsx
// ✅ Good - Semantic colors (theme-aware)
<div className="bg-base-100 text-base-content">
  <span className="text-primary">Primary action</span>
  <span className="text-secondary">Secondary info</span>
  <span className="text-accent">Accent highlight</span>
  <span className="text-success">Success message</span>
  <span className="text-error">Error message</span>
  <span className="text-warning">Warning message</span>
  <span className="text-info">Info message</span>
</div>

// ❌ Bad - Hardcoded colors
<div className="bg-white text-black">
  <span className="text-blue-500">Primary</span>
  <span className="text-red-500">Error</span>
</div>
```

### Color Palette Reference

| Color               | Usage                                    |
| ------------------- | ---------------------------------------- |
| `base-100`          | Main background                          |
| `base-200`          | Secondary background (cards, sidebar)    |
| `base-300`          | Borders, dividers                        |
| `base-content`      | Main text color                          |
| `primary`           | Primary actions, links                   |
| `primary-content`   | Text on primary background               |
| `secondary`         | Secondary actions                        |
| `accent`            | Highlights, special elements             |
| `neutral`           | Active states, selected items            |
| `success`           | Success states, confirmations            |
| `warning`           | Warning states, cautions                 |
| `error`             | Error states, destructive actions        |
| `info`              | Informational states                     |

### Opacity Modifiers

```tsx
// Use opacity modifiers for subtle text
<span className="text-base-content/70">Secondary text</span>
<span className="text-base-content/50">Placeholder text</span>
```

---

## Component Design

### DaisyUI Component Classes

Use DaisyUI's component classes as the foundation:

```tsx
// Buttons
<button className="btn btn-primary">Primary</button>
<button className="btn btn-secondary btn-sm">Small Secondary</button>
<button className="btn btn-outline">Outlined</button>
<button className="btn btn-ghost">Ghost</button>

// Cards
<div className="card bg-base-100 shadow-md">
  <div className="card-body">
    <h2 className="card-title">Title</h2>
    <p>Content</p>
  </div>
</div>

// Form inputs
<input className="input input-bordered w-full" />
<select className="select select-bordered">...</select>
<textarea className="textarea textarea-bordered" />

// Badges
<span className="badge badge-primary">Active</span>
<span className="badge badge-success">Success</span>
<span className="badge badge-error">Error</span>

// Tables
<table className="table table-zebra">...</table>
```

### Rich Interactive Design System

QDash enhances DaisyUI with the "Rich Interactive Design System" (defined in `globals.css`):

| Element        | Enhancement                                               |
| -------------- | --------------------------------------------------------- |
| **Cards**      | Subtle border, deeper shadows on hover                    |
| **Buttons**    | Gradient backgrounds, lift effect on hover, inner glow    |
| **Inputs**     | 2px border, color change on hover, ring + shadow on focus |
| **Badges**     | Fully rounded (pill shape), gradient backgrounds          |
| **Dropdowns**  | Fade-in animation, rich shadows                           |
| **Tables**     | Row hover highlights with primary color tint              |
| **Scrollbars** | Custom styled with gradient thumb                         |

### Interactive Cards

Use utility classes for interactive card behaviors:

```tsx
// Static card (default)
<div className="card">...</div>

// Hoverable card with lift effect
<div className="card card-hover">...</div>

// Clickable/interactive card
<div className="card card-interactive">...</div>

// Glass effect card
<div className="card card-glass">...</div>
```

---

## Empty States

### Use the EmptyState Component

For consistent empty state handling, use the `EmptyState` component:

```tsx
import { EmptyState, EmptyStates } from "@/components/ui/EmptyState";

// Custom empty state
<EmptyState
  title="No tasks found"
  description="Create a new task to get started."
  emoji="rocket"
  size="md"
  action={<button className="btn btn-primary">Create Task</button>}
/>

// Pre-configured empty states
<EmptyStates.noData />
<EmptyStates.noResults />
<EmptyStates.noTasks />
<EmptyStates.error />
```

### Empty State Guidelines

| Scenario        | Emoji               | Title                    | Include Action? |
| --------------- | ------------------- | ------------------------ | --------------- |
| No data         | `empty`             | "No data available"      | Optional        |
| No search match | `magnifying-glass`  | "No results found"       | Yes (clear)     |
| No items        | `rocket`            | "Get started"            | Yes (create)    |
| Error state     | `warning`           | "Something went wrong"   | Yes (retry)     |
| Loading         | `hourglass`         | "Loading..."             | No              |

---

## Loading States

### DaisyUI Loading Classes

```tsx
// Spinner
<span className="loading loading-spinner loading-md" />
<span className="loading loading-spinner loading-sm" />
<span className="loading loading-spinner loading-lg" />

// Alternative styles
<span className="loading loading-dots" />
<span className="loading loading-ring" />
<span className="loading loading-bars" />

// Colored spinner
<span className="loading loading-spinner text-primary" />
```

### Loading State Patterns

```tsx
// Full page loading
<div className="flex justify-center items-center min-h-[400px]">
  <span className="loading loading-spinner loading-lg" />
</div>

// Inline loading
<button className="btn btn-primary" disabled>
  <span className="loading loading-spinner loading-sm" />
  Loading...
</button>

// Skeleton loading (for content)
<div className="skeleton h-4 w-full" />
<div className="skeleton h-32 w-full" />
```

### React Query Loading States

```tsx
const { data, isLoading, isError } = useQuery({...});

if (isLoading) {
  return (
    <div className="flex justify-center items-center py-10">
      <span className="loading loading-spinner loading-lg" />
    </div>
  );
}

if (isError) {
  return <EmptyStates.error />;
}
```

---

## Feedback & Notifications

### Toast System

QDash uses a custom toast system with FluentEmoji:

```tsx
import { useToast } from "@/components/ui/Toast/ToastContext";

const { showToast } = useToast();

// Success toast
showToast("Operation completed successfully", "success");

// Error toast
showToast("Failed to save changes", "error");

// Warning toast
showToast("Please check your input", "warning");

// Info toast
showToast("New updates available", "info");
```

### Inline Feedback

```tsx
// Success message
<div className="alert alert-success">
  <FluentEmoji name="success" size={20} />
  <span>Changes saved successfully</span>
</div>

// Error message
<div className="alert alert-error">
  <FluentEmoji name="error" size={20} />
  <span>An error occurred</span>
</div>
```

---

## Animation & Transitions

### Performance Guidelines

**Only apply transitions to interactive elements** to prevent animation jank on data-heavy pages:

```tsx
// ✅ Good - Transitions are applied automatically by globals.css
<button className="btn btn-primary">Click me</button>
<div className="card">Card content</div>

// ✅ Good - Use transition: none for data-heavy lists
<table className="table">
  {/* Table rows have transition: none by default */}
</table>

// ❌ Bad - Don't add transition-all to list items
{items.map((item) => (
  <div className="transition-all duration-300">{item}</div>  // Causes jank
))}
```

### Available Animation Classes

```tsx
// Page transitions
<div className="page-transition">...</div>
<div className="page-transition-fast">...</div>

// Stagger animation for lists (up to 8 items)
{items.map((item, i) => (
  <div className="stagger-item" key={i}>...</div>
))}

// Status animations
<span className="status-pulse">Running</span>
<span className="status-glow">Active</span>
<span className="animate-success">Done!</span>
```

### Reduced Motion Support

The design system automatically respects `prefers-reduced-motion`:

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## Accessibility

### Focus States

All interactive elements have visible focus states:

```tsx
// Button focus ring is automatic
<button className="btn btn-primary">Focus me</button>

// Input focus states are automatic
<input className="input input-bordered" />
```

### ARIA Labels

Always provide descriptive labels:

```tsx
// ✅ Good
<button aria-label="Close menu" className="btn btn-ghost">
  <X size={20} />
</button>

<input
  type="text"
  aria-label="Search tasks"
  placeholder="Search..."
/>

// ❌ Bad
<button className="btn btn-ghost">
  <X size={20} />
</button>
```

### Color Contrast

Semantic colors are designed for sufficient contrast. When using opacity modifiers:

```tsx
// ✅ Good - Sufficient contrast
<span className="text-base-content/70">Secondary text</span>

// ⚠️ Caution - May have insufficient contrast
<span className="text-base-content/30">Very light text</span>
```

---

## Acceptable Exceptions

While semantic colors should be the default, the following cases permit hardcoded Tailwind colors:

### 1. Global Error Page (`global-error.tsx`)

Next.js global error pages render **outside the app context** where theme providers are unavailable. Hardcoded colors are acceptable here.

```tsx
// ✅ Acceptable - No theme context available
<div className="bg-gray-100">
  <button className="bg-blue-600 text-white">Try Again</button>
</div>
```

### 2. Data Visualization Color Coding

Scientific data visualization often requires **fixed, distinguishable colors** for data series identification:

```tsx
// ✅ Acceptable - Data series must be visually distinct
const parameterColors = {
  t1: "text-blue-600",
  t2_echo: "text-purple-600",
  t2_star: "text-green-600",
  gate_fidelity: "text-red-600",
};
```

### 3. File Type Icons

VSCode-style file type coloring improves recognition and is an established UX pattern:

```tsx
// ✅ Acceptable - File type recognition
<FolderOpen className="text-yellow-600" />  // Folders
<FileJson className="text-yellow-500" />    // JSON files
<FileCode2 className="text-blue-400" />     // Code files
<File className="text-gray-400" />          // Generic files
```

### 4. Rank/Grade Systems

Gamification elements like performance ranks use universal color associations:

```tsx
// ✅ Acceptable - Universal rank associations
const ranks = {
  S: { color: "text-yellow-500", bg: "bg-yellow-100" },  // Gold
  A: { color: "text-green-500", bg: "bg-green-100" },    // Green
  B: { color: "text-blue-500", bg: "bg-blue-100" },      // Blue
  F: { color: "text-red-500", bg: "bg-red-100" },        // Red
};
```

### When NOT to Use Exceptions

```tsx
// ❌ Bad - Use semantic colors for these cases
<div className="text-red-500">Error message</div>     // Use text-error
<button className="bg-blue-500">Submit</button>       // Use btn-primary
<span className="text-green-500">Success!</span>      // Use text-success
```

---

## Quick Reference

### Icon Checklist

- [ ] Use `lucide-react` for all icons
- [ ] Use consistent sizes (18px nav, 20px buttons, 24px headers)
- [ ] Import only the icons you need

### Emoji Checklist

- [ ] Use `FluentEmoji` for empty states and decorative elements
- [ ] Use `getAvatarEmoji()` for user avatars
- [ ] Match emoji to context (status, empty state, decorative)

### Color Checklist

- [ ] Use semantic colors (`text-primary`, `bg-base-100`)
- [ ] Avoid hardcoded colors unless in [Acceptable Exceptions](#acceptable-exceptions)
- [ ] Use opacity modifiers for subtle text (`text-base-content/70`)

### Component Checklist

- [ ] Use DaisyUI component classes
- [ ] Don't override Rich Interactive Design System styles
- [ ] Use `card-hover` for clickable cards
- [ ] Use `EmptyState` for empty state handling

### Animation Checklist

- [ ] Don't add `transition-all` to list items
- [ ] Use `page-transition` for page-level animations
- [ ] Use `stagger-item` for sequential list animations
- [ ] Let globals.css handle interactive element transitions

### Accessibility Checklist

- [ ] Add `aria-label` to icon-only buttons
- [ ] Ensure sufficient color contrast
- [ ] Test with keyboard navigation
- [ ] Respect reduced motion preferences

---

## References

- [Lucide React](https://lucide.dev/guide/packages/lucide-react)
- [Microsoft Fluent Emoji](https://github.com/microsoft/fluentui-emoji)
- [DaisyUI Components](https://daisyui.com/components/)
- [Tailwind CSS](https://tailwindcss.com/docs)
- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
