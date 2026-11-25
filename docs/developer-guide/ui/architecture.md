# UI Architecture

The UI owns routing, interactions, and visualization; the API owns project data and permissions.

## Responsibility Boundaries

| Location under `ui/src/` | Owns |
| --- | --- |
| `app/` | Thin route entries and layouts |
| `components/features/` | Feature behavior and `*PageContent` components |
| `components/ui/` | Shared primitives |
| `components/charts/` | Charts |
| `components/layout/` | Navigation and global layout |
| `contexts/` | Cross-route state |
| `hooks/url-state/` | Shareable filters through `nuqs` |
| `client/`, `schemas/` | Generated API hooks and types |

## Route and Layout Model

`app/(public)/` holds login; `app/(auth)/` holds authenticated pages. `proxy.ts` handles page
redirects, but backend authorization remains authoritative. Caddy sends `/api` directly to
FastAPI, including chat streams; Next.js must not add API rewrites or route handlers.

## Provider Order

Preserve the dependency order in `ui/src/app/providers.tsx`: query client, URL adapter,
authentication, Axios, project, theme, tooltip, then link hover cards. Feature code reuses
these providers instead of adding duplicates.

## API Data Flow

Generated hooks call `ui/src/lib/api/custom-instance.ts`, which adds authentication and project
headers. Mutations invalidate affected queries; project changes invalidate cached data.
See [API Integration](./api-integration.md) for project-specific keys and request headers.

## State Ownership

| State | Owner |
| --- | --- |
| Server records | TanStack Query |
| Shareable filters | `nuqs` URL-state hooks |
| Authentication, project, theme | Context |
| Local interaction | React state or a focused hook |
| Multi-field forms | React Hook Form and Zod |

Use `useProject()` rather than reading browser storage. Keep server records out of duplicate
context state.

## User Avatars

`UserAvatar` renders validated glyph specs locally; the API stores specs, never SVG.
Automatic avatars are the fallback. Custom-spec caches belong to one authenticated session;
a token change clears them and stale responses cannot populate the next session.
When upgrading the generator, update `ui/package.json` and `GLYPH_AVATAR_VERSION` in both
`ui/src/lib/avatar/glyphAvatar.ts` and `src/qdash/api/services/user_avatar_service.py` together.

## Trace an Existing Page

For a first change, open `ui/src/app/(auth)/chip/page.tsx`, then
`ui/src/components/features/chip/ChipPageContent.tsx`. Its project/chip behavior is covered by
`ui/src/components/features/chip/__tests__/ChipPageContent.projectChip.test.tsx`.
Change the feature component and its focused test; leave the route as a thin entrypoint.

## Add a Page

1. Add a thin route and a named feature component.
2. Use generated hooks and existing URL-state hooks.
3. Add sidebar navigation in `ui/src/components/layout/navigation.ts` when needed.
4. Add focused tests and follow [UI Testing](./testing.md).

Placement, exports, and shared controls follow [UI Development Guidelines](./guidelines.md).
