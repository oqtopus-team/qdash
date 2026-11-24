# TypeScript SDK

`@oqtopus-team/qdash-sdk` contains a Fern-generated API client and QDash-specific helpers.
It does not depend on `@oqtopus-team/qdash-client`; existing client applications remain
supported. The server owns authorization and execution.

## Responsibility boundary

| Layer | Owns |
| --- | --- |
| Generated SDK code | API resources, wire types, HTTP request construction |
| Handwritten SDK code | Configuration, authentication, retry policy, run handles, definitions, compound reads |
| Host such as pi-qdash | User context, approvals, tool schemas, presentation |
| API | Catalog, validation, project access, dispatch |

Constructing a session, chip, or definition sends no request. Validation does not execute;
execution does not silently call a separate validation request first.

## Project scope

`new QDash(config, options)` captures a frozen configuration snapshot. `withProject(projectId)`
creates another session sharing authentication and fetch configuration without changing the
original. Without a configured project, the API uses the user's default.
Unlike the Python SDK, TypeScript dispatch permits that default-project behavior.

Run handles poll the whole pipeline, tolerate an initial execution 404, and preserve failed or
cancelled outcomes. Polling sleeps stop at the deadline, but an in-flight read is not cancelled.
Association/idempotency response mismatches raise `QDashResultUnknownError` and require
reconciliation, not a new launch key; see [Calibration Sessions](../agent/calibration-sessions.md).

## Metric scripts and dashboards

`Script`, `Dashboard`, saved revisions, and optimistic updates follow the
[Python SDK semantics](./python-sdk.md#metric-scripts-and-dashboards), with camelCase names.
`Script.fromFile` reads text; it never executes Python. Panels pin saved script revisions.

`taskResults.compareLatest` combines client reads and checks result identity before comparing
values. Keep this reusable comparison logic in the SDK rather than duplicating it in tool hosts.

`taskResults.evidence` joins a result with its execution and current target state. Secondary
read failures remain explicit context states. A caller can name a cooldown to check, but the
SDK never infers a cooldown association that the result API does not expose. See the
[result context contract](../../reference/clients/typescript.md#read-a-result-with-context).

## Configuration and transport

`QDash.fromEnv()` reads environment variables; `await QDash.fromProfile()` reads the same TOML
file and snake_case profile keys as Python. Explicit profile selection overrides `default_profile`,
then `"default"`. INI is a deprecated fallback only when TOML is absent, or when an INI path is
explicit. A bad TOML file never triggers fallback. Shared fixtures in `sdks/testdata/` verify both
implementations. See [configuration](../../reference/clients/typescript.md#configuration).

`qdash.api` exposes generated resources with the session's auth and project header. Generated
retries default to zero. Helpers add one GET retry layer; writes are sent once, including on
409, 5xx, and timeout. Caller aborts are not retried. Helpers translate errors into SDK types;
direct resource calls retain generated errors. Proxy or custom TLS configuration requires a
caller-supplied fetch implementation. Password login validates its response and shares its token
between scoped sessions. A resource 401 invalidates only the sign-in used for that request;
the next call authenticates again without replaying the failed request.

## Generation

`docs/oas/openapi.json` is the only API source. `sdks/typescript/fern/` pins the Fern CLI and
TypeScript generator and configures snake_case wire fields, global project headers, and no
retries. Run `task generate-typescript-sdk` with Node.js (`npx`) and Docker available.
`task generate` also regenerates the SDK. Never edit `src/_generated/` manually.

`task check-typescript-sdk-generated` regenerates and compares output. New API operations
become available through `qdash.api`; handwritten helpers are reserved for composition and
QDash-specific behavior. The generator's inline-type option is disabled to avoid unresolved
nested types. TypeScript declarations are emitted with `tsc` to preserve generated namespaces.

## Packaging and release

The package is ESM and requires Node.js 20 or later. It installs independently of the legacy
client, with `ini` and `smol-toml` for profile parsing. Distribution tests install the packed SDK
outside the workspace and check Node.js, Bun, and TypeScript declarations. See
[Pi Packages](../agent/packages.md#distribution). The pi-qdash adapter builds SDK sessions from
its existing connection settings while retaining legacy client operations where needed.

## Implementation Files

| File | Responsibility |
| --- | --- |
| `sdks/typescript/src/session.ts` | Scoped session |
| `sdks/typescript/src/config.ts` | TOML, INI compatibility, environment configuration |
| `sdks/typescript/src/_http.ts` | Authentication, read retries, error translation |
| `sdks/typescript/src/errors.ts` | SDK exception types |
| `sdks/typescript/src/types.ts` | Public helper type aliases |
| `sdks/typescript/src/_generated/` | Generated API resources and types |
| `sdks/typescript/scripts/generate.mjs` | Reproducible generation and freshness check |
| `sdks/typescript/src/pipelines.ts` | Pipeline and chip operations |
| `sdks/typescript/src/workflows.ts` | Registered workflows |
| `sdks/typescript/src/results.ts` | Compound result operations |
| `sdks/typescript/src/evidence.ts` | Result context joins and typed partial failures |
| `sdks/typescript/src/dashboards.ts` | Script and dashboard authoring |

## Tests

Run `task test-sdk-ts` from the repository root; it checks generated freshness and runs the
typecheck and tests under `sdks/typescript/tests/`. Use recording transports to verify request
bodies, scope, no implicit execution, whole-run polling, revision conflicts, and comparison identity.
When API contracts change, run `task generate` before updating SDK code and fixtures.
