# API Integration

Use the generated TanStack Query client for backend requests.

## Generation Boundary

`ui/orval.config.cjs` generates `ui/src/client/` and `ui/src/schemas/` from OpenAPI.
Do not edit those directories. After a backend contract change, run `task generate` at the
repository root and review both generated surfaces.

## Use Generated Queries

Import hooks from `@/client/<tag>/<tag>`. Their data is an Axios response; the response body is
under `response.data`:

```typescript
import { useListChips } from "@/client/chip/chip";

export function useChipList() {
  const query = useListChips({ query: { staleTime: 30_000 } });
  return { ...query, chips: query.data?.data.chips ?? [] };
}
```

Check `isPending` and `isError` before displaying an empty chip list.
Pass query options through `query`. Use `enabled` while required inputs are missing, rather than
sending placeholder IDs.

## Use Generated Mutations

Pass path parameters and the request body in the generated mutation's argument object.
On success, invalidate every affected view with the exported query-key helpers, such as
`getListChipsQueryKey()`. Do not invent parallel string keys.

## Shared Request Behavior

`ui/src/lib/api/custom-instance.ts` supplies cancellation, bearer authentication, and the active
project header. The default URL is `/api`; host configuration can use `NEXT_PUBLIC_API_URL`.
Docker builds use the same-origin `/api` proxy. Do not create a second Axios instance to bypass
authorization or project errors.

A generated key may lack the project ID even though its data is project-scoped. For such queries,
include the project in the key, enable only when it is present, and pin the request to it:

```typescript
import { useGetExecutionActivity, getGetExecutionActivityQueryKey } from "@/client/execution/execution";
import { useProject } from "@/contexts/ProjectContext";

export function useProjectActivity() {
  const { projectId } = useProject();
  const params = { days: 30 };
  return useGetExecutionActivity(params, {
    query: {
      queryKey: [...getGetExecutionActivityQueryKey(params), projectId],
      enabled: Boolean(projectId),
    },
    request: projectId ? { headers: { "X-Project-Id": projectId } } : undefined,
  });
}
```

## Add Feature Composition

Put multi-query composition in a focused hook under `ui/src/hooks/`. Keep transport and schema
ownership in the generated client. Test request construction and invalidation; for contract
changes run `task generate`, `task test-ui`, and `task ci-ui`.
