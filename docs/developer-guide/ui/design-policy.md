# UI Design Policy

Make calibration data readable, theme-aware, and keyboard accessible.

## Build the Hierarchy Deliberately

Keep scope, labels, units, and status visible. Use base surfaces and reserve `primary` for the
main action. Secondary actions use default, ghost, or outline buttons. Destructive actions use
error intent and confirmation when hard to reverse.

## Use the Established Visual Vocabulary

| Need | Component |
| --- | --- |
| Page framing | `PageContainer`, `PageHeader` |
| Empty state | `EmptyState` |
| User identity | `UserAvatar` |
| Qubit or coupling ID | `QubitTile` |
| Status | DaisyUI badge plus text |
| Confirmation | `ConfirmDialog` or `Dialog` |
| Icon | Lucide React |

## Use Semantic Color

Use DaisyUI `base-*` colors for structure and matching `*-content` colors on filled semantic
backgrounds. Do not add `dark:` overrides for semantic colors. Status must also have text or an
icon. Fixed colors are reserved for meaningful data categories and must work across themes.

## Implement Styles

Start with DaisyUI components, then add Tailwind layout utilities. Shared rules belong in
`ui/src/app/globals.css`; local layout stays with the component. Follow
[UI Development Guidelines](./guidelines.md) for typography, surfaces, and control spacing.
When adding a theme, update `ui/src/constants/themes.ts` and its CSS import and check charts,
dialogs, status colors, and focus indicators.

## Represent Every UI State

| State | Treatment |
| --- | --- |
| Initial load | Skeleton or bounded loader |
| Pending action | Disable its control and show progress |
| Empty | Context and next action |
| Error | Inline message near failed content |
| Successful mutation | Outcome after server confirmation |
| Invalid field | Associated field message |

Keep existing content visible during background refreshes.

## Choose Interaction Behavior Before Appearance

Use established Radix wrappers for focus management, keyboard navigation, portals, and dismissal.
Dialogs need a visible title, safe Escape behavior, and focus restoration. Every control needs
an accessible name and visible keyboard focus; form errors must identify their field.

## Keep Motion Functional

Animate only to explain a transition or ongoing work, respect reduced motion, and avoid looping
dashboard decoration. Menus and popovers animate from their trigger. Test keyboard and focus
behavior for new interactions; see [UI Testing](./testing.md).
