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

`ui/src/app/api/copilot/chat/route.ts` is the browser-facing proxy for the streaming chat route.
Other API calls use the generated client through the Next.js `/api` rewrite or
`NEXT_PUBLIC_API_URL`.

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
