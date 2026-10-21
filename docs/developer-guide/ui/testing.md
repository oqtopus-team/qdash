# UI Testing

UI verification combines focused Vitest tests with type, lint, formatting, unused-code, audit,
and production-build checks.

## Choose the Verification Scope

| Change | Minimum verification |
| --- | --- |
| Pure utility or URL-state hook | Focused Vitest file |
| Component behavior | Focused Testing Library test and `task test-ui` |
| Generated-client integration | Feature tests, TypeScript, and affected API generation checks |
| Route, provider, or shared primitive | `task ci-ui` and `task ci-ui-build` |
| Dependency or build configuration | `task ci-ui`, audit, and production build |

Run broader checks when a shared component, context, navigation rule, or generated contract has
many consumers.

## Run Tests

From the repository root:

```bash
task test-ui
task ci-ui
task ci-ui-build
```

From `ui/`, use Vitest directly for a focused loop:

```bash
bun run test:run src/components/ui/__tests__/Dialog.test.tsx
bun run test:run src/hooks/url-state/__tests__/useMetricsUrlState.test.ts
bun run test -- src/components/features/tasks/__tests__/TaskWorkbenchRun.test.tsx
```

`task ci-ui` runs unit tests, Next.js type generation, TypeScript, Oxlint, Oxfmt, Knip, and the Bun
audit. The production build is intentionally separate in `task ci-ui-build`.

## Place Tests Beside Their Layer

Component tests live in a sibling `__tests__/` directory. Hook tests live under
`ui/src/hooks/__tests__/` or `ui/src/hooks/url-state/__tests__/`. Name a test file after the module
or user-visible behavior it protects.

`ui/vitest.config.mts` uses jsdom and loads `ui/vitest.setup.ts`. The setup provides jest-dom,
`ResizeObserver`, `scrollIntoView`, and `matchMedia`; do not recreate those mocks in each test.

## Test Observable Behavior

Render the component, perform the user action, and assert the resulting screen or request. Prefer
queries by role, label, or visible text over class selectors and implementation details.

Cover the states the component owns:

- loading, empty, error, and success;
- enabled, disabled, and pending actions;
- validation and destructive confirmation;
- keyboard interaction and focus for shared primitives;
- URL updates for shareable filters;
- query invalidation or navigation after a successful mutation.

Use `waitFor` or `findBy*` for observable asynchronous completion. Do not use fixed sleeps.

## Mock at the Boundary

Mock generated client hooks when testing feature composition. Keep request-shape assertions in
the feature that builds the request. Mock browser APIs only when `vitest.setup.ts` does not already
provide them.

Reset spies and mutable globals between tests. Avoid mocking the component under test or private
helpers whose behavior is visible through the public interaction.

For TanStack Query behavior, create a fresh `QueryClient` for each test and disable retries when a
failure is part of the scenario. Wrap only the providers the test requires.

## Check Types and Static Rules

Use these focused commands from `ui/` when diagnosing a failure:

```bash
bunx next typegen
bunx tsc --noEmit
bun run lint
bun run fmt:check
bun run knip
```

Do not silence a type or lint error with `any`, an unused-variable rename, or a blanket disable
until the code proves the value is intentionally unconstrained or unused. Keep a narrow disable
next to the unavoidable case and explain why.

## Verify the Production Boundary

`task ci-ui-build` runs the Next.js production build. Run it for route changes, dynamic imports,
provider changes, server/client boundary changes, and configuration that can behave differently
outside Vitest.

Frontend CI runs `task ci-ui` before the build job. A local focused test is not a substitute for
those checks when the change affects a shared boundary.
