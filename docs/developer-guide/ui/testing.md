# UI Testing

Use focused Vitest tests for behavior and the UI checks for shared or production boundaries.

## Run Tests

From the repository root:

```bash
task test-ui
task ci-ui
task ci-ui-build
```

`ci-ui` includes tests, Next.js type generation, TypeScript, lint, formatting, unused-code checks,
and dependency audit. The production build is separate. Run it for route, provider, import,
server/client boundary, or build configuration changes.

For a focused test, run from `ui/`:

```bash
bun run test:run src/components/ui/__tests__/Dialog.test.tsx
```

## Test Observable Behavior

Place tests in a sibling `__tests__/` directory. Reuse `ui/vitest.setup.ts` browser mocks.
Render, act, and assert by role, label, or visible text. Cover the states the component owns:
loading, empty, error, success, pending actions, validation, keyboard behavior, and URL changes.
Use `findBy*` or `waitFor`, never fixed sleeps.

Mock generated hooks for feature composition, not the component under test. For query behavior,
use a fresh query client with retries disabled for expected failures. Reset spies and globals.

## Check Types and Static Rules

From `ui/`:

```bash
bunx next typegen
bunx tsc --noEmit
bun run lint
bun run fmt:check
bun run knip
```

Fix the cause rather than adding blanket type or lint suppressions.

## Audit Exceptions

`.github/scripts/audit-exceptions.mjs` allows only approved advisory IDs in `AUDIT_EXCEPTIONS`.
Other advisories and failed registry requests fail the check. Exceptions expire within 14 days;
renewal needs a new assessment and maintainer approval.

The current `picomatch` exception, GHSA-fc5q-39xc-vjpf, expires on 2026-12-02 at 00:00 UTC.
Its extglob ReDoS risk is limited to patterns from checked-in tooling configuration; a malicious
pattern could stall a tool run. Next.js's bundled copy uses the fixed `images.remotePatterns`
configuration. Remove the exception when a patched version is installed or this exposure changes.
