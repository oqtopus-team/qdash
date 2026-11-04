# API Integration

UI code calls the backend through the Orval-generated TanStack Query client; authentication,
project scope, cancellation, and response typing enter through the shared Axios instance.

## Generation Boundary

`ui/orval.config.cjs` reads `docs/oas/openapi.json` and writes tag-split hooks to
`ui/src/client/` and schemas to `ui/src/schemas/`. Both directories are generated and must not be
edited manually.

After a backend route or schema changes, run from the repository root:

```bash
task generate
```

Review the OpenAPI and generated TypeScript changes together. A surprising client diff usually
means the backend contract needs another look.

## Use Generated Queries

Import a query hook from its generated tag module. The return value is an Axios response, so API
content is under `data.data`:

```tsx
import { useListChips } from "@/client/chip/chip";

const { data: response, isLoading, isError } = useListChips({
  query: { staleTime: 30_000 },
});

const chips = response?.data.chips ?? [];
```

Pass TanStack Query options through the generated `query` property. Use `enabled` when required
route or project input is not ready; do not send placeholder identifiers to the API.

## Use Generated Mutations

Generated mutations accept their path parameters and request body in one object. Invalidate the
generated query key after a successful mutation:

```tsx
import { useQueryClient } from "@tanstack/react-query";
import { getListChipsQueryKey, useCreateChip } from "@/client/chip/chip";

const queryClient = useQueryClient();
const createChip = useCreateChip({
  mutation: {
    onSuccess: () => queryClient.invalidateQueries({ queryKey: getListChipsQueryKey() }),
  },
});

createChip.mutate({ data: request });
```

Invalidate every query whose server representation changed. Prefer exported generated query-key
helpers over handwritten string keys.

## Shared Request Behavior

`ui/src/lib/api/base-url.ts` fixes browser API requests to the same-origin `/api` path;
`NEXT_PUBLIC_API_URL` is not used. Caddy routes this prefix directly to FastAPI in the standard
deployment. When the UI server is opened directly for development, the Next.js rewrite uses
`INTERNAL_API_URL`. The interceptor of the shared Axios instance in
`ui/src/lib/api/custom-instance.ts` adds the bearer token and, unless the request already sets
`X-Project-Id`, the active project header. Its returned promise exposes cancellation for TanStack
Query.

Feature code does not add the bearer token. A missing project or authorization error must be
handled as an application state, not bypassed with another Axios instance.

A query whose parameters do not identify the project, such as project-wide activity, returns
different data for each project under the same generated key. Switching projects invalidates
every query before the old project's components unmount, so that refetch reads the new project
from storage. For such a query, add `projectId` from `useProject()` to the query key, set
`enabled: Boolean(projectId)`, and pin the header to that key's project:

```tsx
const { projectId } = useProject();
useGetExecutionActivity(params, {
  query: {
    queryKey: [...getGetExecutionActivityQueryKey(params), projectId],
    enabled: Boolean(projectId),
  },
  request: projectId ? { headers: { "X-Project-Id": projectId } } : undefined,
});
```

## Add Feature Composition

Create a focused hook under `ui/src/hooks/` when a feature combines generated queries, derives a
stable view model, or coordinates multiple invalidations. Keep transport and schema ownership in
the generated client.

Test request construction and invalidation in the owning feature or hook. Run `task generate`,
`task test-ui`, and `task ci-ui` for a changed API contract.

See [UI Architecture](./architecture.md#api-data-flow) for the full request path.
