# TypeScript SDK

`@oqtopus-team/qdash-sdk` builds domain operations on the generated QDash client. It adds no
transport, retry layer, or cache; the API remains responsible for authorization and execution.

## Responsibility boundary

| Layer | Owns |
| --- | --- |
| Client | Configuration, authentication, HTTP, generated types, errors |
| SDK | Calibration/workflow handles, definitions, and compound reads |
| Host such as pi-qdash | User context, approvals, tool schemas, presentation |
| API | Catalog, validation, project access, dispatch |

Constructing a session, chip, or definition sends no request. Validation does not execute;
execution does not silently call a separate validation request first.

## Project scope

A session's `projectId` uses `client.withProject` without mutating the given client. Without one,
it retains the client's scope; when neither supplies a project, the API uses the user's default.
Unlike the Python SDK, TypeScript dispatch permits that default-project behavior.

Run handles poll the whole pipeline, tolerate an initial execution 404, and preserve failed or
cancelled outcomes. Timeout is not cancellation. Association/idempotency failures require
reconciliation, not a new launch key; see [Calibration Sessions](../agent/calibration-sessions.md).

## Metric scripts and dashboards

`Script`, `Dashboard`, saved revisions, and optimistic updates follow the
[Python SDK semantics](./python-sdk.md#metric-scripts-and-dashboards), with camelCase names.
`Script.fromFile` reads text; it never executes Python. Panels pin saved script revisions.

`taskResults.compareLatest` combines client reads and checks result identity before comparing
values. Keep this reusable comparison logic in the SDK rather than duplicating it in tool hosts.

## Packaging and release

The package is ESM and requires Node.js 20 or later. Workspace development uses `workspace:*`;
release artifacts pin the matching client version and publish after it. See
[Pi Packages](../agent/packages.md#distribution). Examples are in the
[TypeScript client reference](../../reference/clients/typescript.md).

## Implementation Files

| File | Responsibility |
| --- | --- |
| `sdks/typescript/src/session.ts` | Scoped session |
| `sdks/typescript/src/pipelines.ts` | Pipeline and chip operations |
| `sdks/typescript/src/workflows.ts` | Registered workflows |
| `sdks/typescript/src/results.ts` | Compound result comparisons |
| `sdks/typescript/src/dashboards.ts` | Script and dashboard authoring |

## Tests

Run `task test-sdk-ts` from the repository root; it builds the client and runs the typecheck and
tests under `sdks/typescript/tests/`. Use recording transports to verify request
bodies, scope, no implicit execution, whole-run polling, revision conflicts, and comparison identity.
When API contracts change, run `task generate` before updating SDK code and fixtures.
