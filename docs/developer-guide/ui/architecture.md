# UI Architecture

The QDash UI owns browser routing, interaction state, visualization, and authenticated access to
the API. Backend services remain the source of truth for project data and permissions.

## Responsibility Boundaries

| Layer | Location | Responsibility |
| --- | --- | --- |
| Routes | `ui/src/app/` | App Router entry points, layouts, and the Copilot stream proxy |
| Feature UI | `ui/src/components/features/` | Page behavior and feature-specific composition |
| Shared UI | `ui/src/components/ui/` | Reusable interaction and presentation primitives |
| Layout | `ui/src/components/layout/` | Navigation, global indicators, and chat surfaces |
| Context | `ui/src/contexts/` | Authentication, project, theme, and cross-route UI state |
| URL state | `ui/src/hooks/url-state/` | Shareable filters and selections backed by `nuqs` |
| API client | `ui/src/client/`, `ui/src/schemas/` | Generated TanStack Query hooks and schemas |

Route files stay thin. A `page.tsx` selects route parameters and renders a named
`*PageContent` component from `components/features/`; it does not own feature business logic.

## Route and Layout Model

`ui/src/app/(public)/` contains the login route. `ui/src/app/(auth)/` contains authenticated
application routes such as dashboard, workflow, task results, evaluations, knowledge, config, and
settings. Route groups organize layouts without changing URLs.

`ui/src/proxy.ts` redirects unauthenticated page requests to `/login` and redirects an already
authenticated login request to `/execution`. It deliberately passes `/api` requests through;
FastAPI validates their bearer token and project permissions.

Caddy forwards every browser `/api` request to the API, including the Copilot chat stream, both
in Docker Compose and under `task dev-local`. Next.js has no `/api` rewrites or route handlers;
`ui/src/lib/__tests__/nextConfig.test.ts` keeps it that way. See
[Browser Entry Point](../architecture.md#browser-entry-point).

## Provider Order

`ui/src/app/providers.tsx` composes providers in dependency order:

```text
QueryClientProvider
└─ NuqsAdapter
   └─ AuthProvider
      └─ AxiosProvider
         └─ ProjectProvider
            └─ ThemeProvider
               ├─ route content
               └─ ToastContainer
```

Keep this order when adding a provider. `ProjectProvider` uses authenticated generated hooks and
the shared query client, while feature components expect authentication, project, theme, and toast
state to be available.

## API Data Flow

The OpenAPI document generates `ui/src/client/` and `ui/src/schemas/` through
`ui/orval.config.cjs`. Generated hooks call `customInstance` in
`ui/src/lib/api/custom-instance.ts`, which adds the bearer token and active project header and
provides request cancellation.

<Diagram name="ui-data-flow" caption="Request paths from a feature component to FastAPI, and the build-time loop that generates the hooks." />

Do not edit generated files or replace a generated endpoint with an ad hoc request. Change the
backend schema or route, run `task generate`, and add a focused hook only when the feature needs
composition that the generated hook does not provide.

Mutations must invalidate the generated query key for every view whose server state changed.
Project changes invalidate all cached queries because identical route parameters can refer to
different project data.

## State Ownership

Choose the narrowest state owner that preserves the required behavior:

| State | Owner |
| --- | --- |
| API records and mutation status | TanStack Query generated hooks |
| Filters that must survive refresh or be shareable | `nuqs` hooks in `hooks/url-state/` |
| Authentication, active project, theme, global layout | Context under `contexts/` |
| State used by one component subtree | Local React state or a focused hook |
| Validated multi-field form state | React Hook Form with Zod |

`ProjectProvider` resolves the active project from the URL, saved browser selection, user default,
or first accessible project. It writes the selection back to the URL and browser storage, then
invalidates queries when the project changes. Feature code uses `useProject()` instead of reading
that storage directly.

## User Avatars

The browser renders every user avatar locally with the `glyph-avatar` package bundled into the
UI, pinned to exactly `0.1.0`. `UserAvatar` builds a `data:` URI from a canonical spec string
and shows it in an `<img>`, so an avatar makes no image request and its SVG cannot run script.
No CDN or generator service is involved; once the UI assets have loaded, avatars depend only on
the username.

A user without a custom choice shows the automatic spec `v1:<username>::solid:c`. Its seed is the
username, so the same username gets the same avatar on every instance that bundles the same
package version. `UserAvatar` renders this spec immediately and keeps it while avatar data is
loading, when the API or network fails, and when a stored spec fails validation.

A custom choice from the picker in **Settings** is saved per instance as a spec string. The API
validates the spec with `parse_avatar_spec` and stores it in the `user_avatar` collection with
its seed and the generator name and version; it never accepts or stores SVG. Resetting to the
automatic avatar deletes the record. Records written by an earlier development version with
`source: "automatic"`, `svg`, or `etag` fields are ignored when read, and the obsolete fields are
removed when the user saves again, so no migration is needed. The legacy `avatar_key` field on
`user` is left unchanged and unused by the avatar.

`ui/src/lib/avatar/avatarSpecs.ts` loads custom specs for display. It collects the usernames
rendered in the same tick and fetches them with one `GET /users/avatars` request of up to 100
usernames, caches results for five minutes, and retries a failed lookup on a later mount after
30 seconds. Saving in the profile form writes the new spec into this cache, which updates the
sidebar, forum, and every other `UserAvatar` of that user without reloading. The profile form
itself reads and writes the full setting through `GET` and `PUT /auth/me/avatar`.

The cache belongs to one authenticated session. `AuthProvider` calls `startAvatarSpecSession`
whenever the access token changes, so login, logout, and a rejected token discard every cached
spec and queued lookup. Mounted avatars show the automatic avatar at once and look their users
up again when a token is present; no lookup is made without one. A response or profile save
that started in an earlier session is dropped, so a slow request cannot fill the next account's
cache. The session is tracked by object identity and holds no token.

Changing the pinned version changes every automatic avatar and how stored specs render. Update
`ui/package.json`, `GLYPH_AVATAR_VERSION` in `ui/src/lib/avatar/glyphAvatar.ts`, and
`GLYPH_AVATAR_VERSION` in `src/qdash/api/services/user_avatar_service.py` together; tests on
both sides fail when they differ.

## Architectural Invariants

- `page.tsx` and `layout.tsx` use default exports; ordinary modules use named exports.
- Browser-visible API state comes from generated hooks, not duplicate context state.
- Project-scoped requests use the active project supplied by the shared client.
- URL filters use the existing `use*UrlState` hooks so links reproduce the same view.
- Dialogs, menus, and tooltips reuse the established accessible primitives in
  `components/ui/`.
- Route protection improves navigation but never replaces backend authorization.

## Add a Page

1. Add a thin route under `ui/src/app/(auth)/` or `ui/src/app/(public)/`.
2. Add the page content under the matching `ui/src/components/features/` directory.
3. Use a generated client hook for server state and an existing URL-state hook for shareable
   filters.
4. Add navigation in `ui/src/components/layout/navigation.ts` when the page belongs in the
   sidebar.
5. Add focused component or hook tests beside the code.
6. Run `task test-ui`, `task ci-ui`, and `task ci-ui-build` as appropriate for the change.

## Implementation Files

- `ui/src/app/layout.tsx` and `ui/src/app/providers.tsx`
- `ui/src/proxy.ts`
- `ui/src/lib/api/custom-instance.ts`
- `ui/orval.config.cjs`
- `ui/src/contexts/ProjectContext.tsx`
- `ui/src/components/layout/navigation.ts`
- `ui/src/components/ui/UserAvatar.tsx` and `ui/src/lib/avatar/`
- `src/qdash/api/services/user_avatar_service.py` and `src/qdash/api/routers/user_avatar.py`
