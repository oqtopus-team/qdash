# Components and State

QDash components separate reusable interaction behavior from feature-specific composition, while
state stays with the narrowest owner that needs it.

## Choose a Component Location

| Component kind | Location | Example |
| --- | --- | --- |
| Generic interaction or presentation | `components/ui/` | `Dialog`, `DataTable`, `EmptyState` |
| Feature-specific composition | `components/features/<feature>/` | `EvaluationRequestModal` |
| Plot or chart wrapper | `components/charts/` | `Plot`, `PlotCard` |
| Application shell | `components/layout/` | `AppLayout`, `GlobalCommandPalette` |
| Cross-feature selector | `components/selectors/` | `ChipSelector` |

Move a component into `components/ui/` only after its API is independent of a feature model. A
shared visual shape with feature-specific data behavior remains in the feature directory.

## Choose the Interaction Foundation

QDash uses DaisyUI and Radix for different responsibilities:

| Need | Foundation |
| --- | --- |
| Button, card, input, badge, alert, table, loading state | DaisyUI |
| Dialog focus trapping and restoration | `components/ui/Dialog.tsx` |
| Keyboard-aware menu with a portal | `components/ui/DropdownMenu.tsx` |
| Collision-aware accessible tooltip | `components/ui/Tooltip.tsx` |
| Feature layout and spacing | Tailwind utilities |

Reuse the shared Radix wrappers instead of importing Radix packages in feature components. Style
their content with DaisyUI semantic colors so every theme remains readable. Do not introduce a
headless primitive only to replace a working DaisyUI visual component.

## Choose a State Owner

| State lifetime | Owner |
| --- | --- |
| Remote record or request status | Generated TanStack Query hook |
| Shareable or refresh-stable filter | Existing `use*UrlState` hook |
| Cross-route session state | Existing context |
| One component or subtree | Local state or focused custom hook |
| Validated form | React Hook Form and Zod |

Do not copy query results into Context. Do not put a temporary modal flag into a global provider.
When a mutation succeeds, invalidate the affected query key instead of manually synchronizing
multiple copies of the response.

## Reuse Page Primitives

Feature pages should compose the existing primitives before creating new ones:

- `PageContainer` and `PageHeader` establish page width and heading actions.
- `PageFiltersBar` gives filters consistent responsive behavior.
- `DataTable` handles shared table behavior.
- `EmptyState`, `ErrorCard`, `Loader`, and skeletons cover non-success states.
- `ConfirmDialog` covers destructive confirmation.
- `Toast` reports completed background actions or failures that are not tied to one field.

Use field-level text for validation errors and inline alerts when the error belongs to a visible
section. A toast must not be the only place a reader can discover why a form field is invalid.

## Preserve Component Invariants

- Props use explicit interfaces or imported domain types; avoid `any`.
- Interactive elements expose an accessible name and work from the keyboard.
- A component does not fetch data when its parent already owns the same query.
- Lists use stable domain identifiers as keys.
- Loading, empty, error, and success states are distinct.
- Destructive actions require an explicit confirmation unless they are trivially reversible.
- Feature files import generated schemas rather than redefining API response shapes.

## Add a Shared Primitive

1. Search `components/ui/` and feature directories for an existing behavior.
2. Confirm that at least two callers can use a feature-independent API.
3. Choose DaisyUI for visual components or an established Radix wrapper for complex interaction.
4. Add the primitive and its focused test under `components/ui/__tests__/`.
5. Migrate only the callers in scope; avoid a repository-wide visual rewrite in the same change.
6. Document the primitive here only when it establishes a new project-wide rule.

See [Styling](./styling.md) for class and theme rules and [UI Testing](./testing.md) for interaction
tests.
