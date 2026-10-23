# UI Design Policy

QDash UI changes must preserve a theme-aware, keyboard-accessible visual hierarchy across dense
calibration views and focused editing workflows.

## Build the Hierarchy Deliberately

Use base surfaces for most content and reserve the primary color for the page's main action.
Secondary actions use the default, ghost, or outline treatment. Destructive actions use the error
intent and require confirmation when the result is not easily reversible.

Dense scientific views prioritize readable data over decoration. Keep labels, units, selected
scope, and status visible before adding gradients, shadows, or motion.

## Use the Established Visual Vocabulary

| Need | Use |
| --- | --- |
| Interface action or status | Lucide React icon |
| Empty-state illustration | `FluentEmoji` through `EmptyState` |
| User identity | `UserAvatar` |
| Status or count | DaisyUI badge or status color |
| Main page framing | `PageContainer` and `PageHeader` |
| Destructive confirmation | `ConfirmDialog` or shared `Dialog` |

Icons supplement a visible label unless the meaning is conventional and the control has an
accessible name. Use the size already established by neighboring controls; do not use Unicode
symbols or emoji as interface icons.

## Use Semantic Color

Base colors carry structure. `primary` identifies the main action, `secondary` and `accent` are
rare emphasis colors, and status colors retain their standard meanings. Never use color as the
only status signal; pair it with text, an icon, or both.

Use fixed colors only where the same data category must remain stable across themes, such as a
plot series. Verify contrast against every surface on which that color appears.

## Implement Styles

Start with a DaisyUI component class, add its intent or size modifier, then use Tailwind utilities
for local layout and responsive behavior. Do not reproduce a component's base style with a long
utility list or use inline styles for ordinary layout and theme colors.

Use `base-*` colors for surfaces and content. Pair filled semantic backgrounds with their matching
`*-content` foreground. Do not add `dark:` variants for DaisyUI semantic colors; the active
`data-theme` supplies their values.

`ui/src/app/globals.css` owns application-wide theme overrides, shared motion, and behavior that
must apply to every matching component. Keep one-off layout in component classes. Before adding a
global selector, confirm that every matching component should change.

Theme names live in `ui/src/constants/themes.ts`, while their imports and QDash overrides live in
`globals.css`. When adding a theme, update `AVAILABLE_THEMES`, update `DARK_THEMES` when it needs
dark surfaces, import its DaisyUI theme, and check representative pages, dialogs, charts, status
colors, and focus indicators.

## Represent Every UI State

Feature components distinguish these states:

| State | Treatment |
| --- | --- |
| Initial loading | Skeleton when layout is known; loader for a bounded unknown shape |
| Background action | Disable the initiating control and show progress in place |
| Empty result | `EmptyState` with the next available action |
| Recoverable section error | Inline alert or `ErrorCard` near the failed content |
| Completed background action | Toast with the outcome and an optional follow-up action |
| Invalid field | Message associated with the field |

Do not replace existing content with a full-page spinner during a background refetch. Do not show
a success toast before the server confirms the mutation.

## Choose Interaction Behavior Before Appearance

DaisyUI supplies the visual foundation. Use shared Radix primitives when the interaction needs
focus trapping, restoration, keyboard navigation, portals, outside-click dismissal, or collision
handling.

Dialogs have a visible title, a description when context is not obvious, a predictable initial
focus target, Escape dismissal when safe, and focus restoration to the trigger. Menus support
arrow-key navigation and do not hide destructive intent behind an unlabeled icon.

## Keep Motion Functional

Use motion to connect a trigger with its result or to show ongoing work. Avoid continuous or
large-area animation on dashboards, topology grids, tables, and repeated cards. Respect
`prefers-reduced-motion`; `globals.css` supplies the global fallback.

## Meet the Accessibility Baseline

- Every control has an accessible name.
- Keyboard focus remains visible.
- Form errors are associated with their field.
- Dialog and menu focus stays within the active surface.
- Status is expressed in text as well as color.
- Text and meaningful graphics meet contrast requirements in supported themes.
- Interactive targets remain usable at narrow viewport widths.

Test keyboard behavior with Testing Library for shared interactions and verify focus manually for
new composite widgets.

## Allow Exceptions Only for Meaning

Fixed colors are acceptable for data visualization, file-type identity, or a grade scale when the
color itself carries stable domain meaning. A global error route can use a minimal independent
surface because normal providers may be unavailable.

An exception must still provide readable text, accessible names, and sufficient contrast. It is
not a reason to bypass semantic colors for ordinary controls. Component placement and interaction
foundations are defined in [UI Development Guidelines](./guidelines.md#keep-boundaries-explicit).
