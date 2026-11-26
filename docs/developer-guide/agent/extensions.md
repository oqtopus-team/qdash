# Pi Extension Design

Pi extensions own tools and shared skills. The QDash runtime owns authentication, conversation
orchestration, tool exposure, and web context.

## Supported hosts

pi CLI and the web Agent share pi-qdash capabilities and approval policy. Presentation and
host-specific features can differ; test shared logic in both hosts.

## pi-qdash

`packages/pi-qdash/extensions/qdash.ts` registers tools. Domain tools live in `extensions/tools/`;
shared helpers live in `extensions/lib/`.

Keep reusable domain operations in the SDK, tool arguments and approval rules in the extension,
and web presentation in the runtime/UI. `qdash-guidance.ts` supplies shared request policy and
tool routing. Skills describe procedures and read task knowledge instead of duplicating it.

`extensions/lib/tool-intents.ts` maps common tools to request purposes. For classified deferred
tools, `applyToolPolicy` appends purpose words to the description used by Pi's native BM25
`tool_search`. Both hosts include a guide built from the same mapping. This changes search
relevance, not access or the session's tool selection. Update the mapping when adding a tool
for one of these purposes; keep measurement preparation free of writes.

`qdash_get_task_result_evidence` is a presentation adapter over the SDK's
`taskResults.evidence`: the SDK joins authorized reads; the tool bounds and redacts output and
adds web links. Keep reusable joins in the SDK so scripts can use them without Pi.
`qdash_summarize_task_results` similarly delegates pagination, counts, and completeness checks
to `taskResults.summarize`; the tool maps arguments and formats the SDK result.

`extensions/lib/connection.ts` resolves environment, TOML, or legacy INI settings and
creates a TypeScript SDK session. `extensions/lib/qdash-connection.ts` adapts its generated
API calls and responses for pi. Tool requests within one connection share its sign-in,
project, and transport. The hosted runtime supplies its own temporary INI file for each
authenticated connection. Standalone profile selection is described in
[pi-qdash configuration](../../reference/pi-qdash.md#configuration).

Use generated SDK methods for known routes, including list filters and task knowledge Markdown.
Figure downloads use the SDK transport to read the response bytes and headers. Standalone
pi also exposes `qdash_raw_get` for paths supplied explicitly by the caller.

`tests/sdk-adapter-integration.test.mjs` exercises the real adapter and SDK against a local
HTTP server, including project headers, session preflight, single dispatch, and uncertain
outcomes. The launch tools preserve `QDashResultUnknownError` reconciliation guidance rather
than reporting a run as started.

Reviewed writes require user approval. Session-granted tools are limited to the approved session
and still pass server checks. A model-provided approval flag is never authority.

## pi-qcaleval

`packages/pi-qcaleval/extensions/qcaleval.ts` owns evaluator model selection, questions, request
construction, and parsing. It has no QDash client dependency. Hosts provide task evidence and
knowledge through pi-qdash's shared `qcal-hydration.ts`; they must not silently change the
[evaluation protocol](./evaluation.md). For standalone setup, use the
[pi-qcaleval configuration example](../../reference/pi-qcaleval.md#configuration).

## Verify a change

From the repository root:

```bash
bun install --frozen-lockfile
task ci-pi-packages
task ci-agent-runtime
```

For an interactive check, [install pi](../../reference/pi-qdash.md#configuration),
build the client and SDK with `task build-client-ts`, then run
`pi -e ./packages/pi-qdash` or `pi -e ./packages/pi-qcaleval`. `task pi-local` selects the
configured Agent chat model.

Rebuild the web runtime with `docker compose up -d --build agent-runtime`. Verify tool exposure,
argument validation, project scope, approvals, and result rendering in the affected hosts.
[Pi Packages](./packages.md) covers packaging and releases.
