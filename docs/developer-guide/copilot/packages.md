# Pi Packages

QDash maintains two separately published pi extensions in its root Bun workspace,
alongside `agent-runtime/`, `clients/typescript/`, and `sdks/typescript/`. The runtime uses the source in the checkout; npm packages
serve standalone pi CLI users.

| Directory | npm package | Stable release |
| --- | --- | --- |
| `packages/pi-qdash/` | `@oqtopus-team/pi-qdash` | QDash `vX.Y.Z` tag, as `X.Y.Z` |
| `packages/pi-qcaleval/` | `@oqtopus-team/pi-qcaleval` | QDash `vX.Y.Z` tag, as `X.Y.Z` |

pi-qdash depends on `@oqtopus-team/qdash-client` and the TypeScript SDK
`@oqtopus-team/qdash-sdk` through `workspace:*`, and the SDK depends on the client
the same way, so API, client, SDK, and tool changes can be tested in one PR. The root lockfile also owns the
client's dependency overrides. The UI and documentation retain separate Bun
installs; the Python client retains its Python workspace configuration.
pi-qcaleval has no QDash client or runtime dependency.

The [pi-qdash](../../reference/pi-qdash.md) and
[pi-qcaleval](../../reference/pi-qcaleval.md) references describe their public tools.
See [Pi Extension Design](./extensions.md) for the extension and skill boundaries.

## Development

Install from the repository root with Bun 1.4.0. Package tests also require Node.js 24.

```bash
bun install --frozen-lockfile
task test-client-ts
task test-sdk-ts
task ci-pi-packages
task ci-agent-runtime
```

The root `bun.lock` covers the runtime, client, SDK, and both extensions. Do not create
package-local lockfiles. `task ci-pi-packages` and `task ci-agent-runtime` build
the client and SDK first; run `task build-client-ts` before using pi CLI directly. Test standalone pi behavior with `pi -e ./packages/pi-qdash` or
`pi -e ./packages/pi-qcaleval` from the repository root. `task pi-local` runs pi-qdash with the Copilot chat model; see
[Verify a change](./extensions.md#verify-a-change).

Rebuild the runtime with `docker compose up -d --build agent-runtime` after changing
an extension or its skills. The [runtime extension loader](./architecture.md#developing-a-pi-extension-against-the-runtime)
loads both packages and retains pi-qdash's tool allowlist and write approvals.
Additional checkouts under `agent-runtime/extensions/` can override a bundled package.

Evaluation records identify a bundled evaluator by its package name and version,
with a `+source.<hash>` suffix. The hash covers its manifest, extension code, skills,
and the root lockfile, so an unpublished code or dependency change gets a different
identity even when the Docker image has no Git metadata. This suffix is runtime
metadata; npm releases use the versions described below.

## Distribution

`.github/workflows/publish-typescript-packages.yml` is the common QDash release pipeline:
it validates PRs, publishes beta builds from `develop`, and publishes stable versions
from the QDash `vX.Y.Z` tag pushed after a release PR merges into `main`. Both pi
packages, both clients, and both SDKs share QDash's version, so one QDash tag releases all six as
`X.Y.Z`; there are no package-specific release tags.
It calls the reusable `publish-qdash-typescript-client.yml`, which has no triggers of its
own, to build the matching client; when publishing, that call must publish the client
successfully first. The `sdk` job then checks, packs, and verifies the npm SDK at the
client's exact version, and `publish-sdk` publishes it before either pi package publishes.
Both packages publish under `@oqtopus-team`.
pi-qcaleval moves from `@orangekame3/pi-qcaleval` to `@oqtopus-team/pi-qcaleval`;
pi-qdash keeps its existing name.

| Trigger | Result |
| --- | --- |
| PR to `develop` affecting packages, either client, either SDK, API schema, runtime, root dependencies, or release workflow | Typecheck and test the SDK, both packages, and runtime; upload npm tarballs without publishing |
| Push to `develop` affecting packages, either client, either SDK, API schema, root dependencies, or release workflow | Publish the client beta first, then the npm SDK beta, then both pi betas, with the `beta` dist-tag; then publish `qdash-client` and `qdash-sdk` of the same version to PyPI |
| QDash `vX.Y.Z` tag | Publish the client, then the npm SDK, then both pi packages, as `X.Y.Z` under `latest`; then publish `qdash-client` and `qdash-sdk` `X.Y.Z` to PyPI |
| Manual run on a branch | Build and validate without publishing |
| Manual run on a QDash tag | Retry that stable release; versions already on npm are skipped |

Before packing, `.github/scripts/sdk-package-release.mjs` sets the npm SDK's version to
the exact client version returned by the client workflow and pins its client dependency to
it, and the pi release script replaces pi-qdash's `workspace:*` client and SDK dependencies
with that same version, so a QDash tag packs pi-qdash `X.Y.Z` with client and SDK `X.Y.Z`.
Both reject missing versions and `0.0.0`. The source manifests
retain their development versions; releases never read them. Artifact checks
install the client and SDK tarballs, and then those with pi-qdash, in separate npm
consumers and check for one client copy; PR checks therefore do not need either to exist
on npm yet.

Client versions follow QDash, as described in the
[TypeScript client reference](../../reference/clients/typescript.md#installation):
`X.Y.Z` on a QDash tag and `<next QDash patch>-beta.<build>` on `develop`, where
`<build>` counts first-parent commits. QDash tags live on `main`, so the next patch
comes from the highest `vX.Y.Z` tag present when a run starts, and a later run of the
same commit can compute a later patch. Every package therefore takes its version from
one computation per run:

1. The reusable client workflow computes the npm version and its PEP 440 spelling once,
   publishes the npm client, and then uploads a `qdash-client-release` artifact holding
   the commit, ref, run ID, channel, and both spellings.
2. The npm SDK job takes the same client version as its own. The pi build jobs receive
   the same client version and derive their own with
   `releaseVersion` in `.github/scripts/pi-package-release.mjs`.
3. When this workflow's run completes, `publish-qdash-client.yml` starts through
   `workflow_run`, verifies the run and its record with `pypiRelease` in
   `.github/scripts/client-release.mjs`, then checks out the verified commit, builds
   `qdash-client` and `qdash-sdk` with that exact version, publishes `qdash-client`, and
   then publishes `qdash-sdk`, which requires `qdash-client==<version>`.

pi betas keep a run-based suffix on the same base:
`<next QDash patch>-beta.<GitHub run ID>.<attempt>` (for example
`1.10.3-beta.12345678.1` beside client `1.10.3-beta.1278`). The attempt makes a retry
publishable when one package published before the other failed. pi-qdash pins the
client beta from the same run.

`workflow_run` reports the triggering ref only as a short name such as `v1.9.21`, which
can name a branch as well as a tag, and anyone who can push a branch can start this
workflow's run on it. `publish-qdash-client.yml` therefore runs `pypiRelease` from a
checkout of the default branch, before it checks out or runs the triggering commit, and
publishes only in two cases:

| Channel | Accepted run | Remote check |
| --- | --- | --- |
| `latest` | Push or manual run of `publish-typescript-packages.yml` on QDash tag `vX.Y.Z` in this repository | `refs/tags/vX.Y.Z` resolves to the run's commit, that commit is on `main`, and no branch `vX.Y.Z` exists |
| `beta` | Push to `develop` in this repository | The run's commit is on `develop` |

The record must have exactly the expected fields and name the run's commit, ref, and run
ID, with versions that match the channel; anything else fails before any repository code
from the triggering commit runs. Who may push `vX.Y.Z` tags and `develop` is a repository
setting; keep both protected, because an accepted tag publishes its commit to PyPI.

`publish-qdash-client.yml` has no push or tag trigger of its own; on PRs and manual runs
it only validates. It ignores PR runs of this workflow. Registries and packages publish
in separate jobs and runs, so a release is not atomic: if the PyPI run fails, rerun that
run, which reuses the same record; if a pi package fails, rerun the failed jobs.
`qdash-sdk` publishes only after `qdash-client` succeeds, so PyPI never has an SDK whose
client is missing. If the SDK job fails after the client published, rerun the failed jobs:
they reuse the run's built files, and PyPI skips the client version already uploaded. A run
that fails before publishing the npm client uploads no record, and its PyPI run fails
at the download step. A rerun on a QDash tag skips every `X.Y.Z` that npm already has,
through `publishTag` for the pi packages and `sdkPublishTag` for the npm SDK, and PyPI
skips an existing version. If the npm SDK fails to publish, the pi packages do not
publish in that run; rerun the failed jobs. A tag older
than a package's npm `latest` fails instead of moving `latest` back. On `develop`, a full rerun
without a new QDash tag skips the published client and npm SDK and publishes pi betas under the new
attempt; after a new QDash tag, it computes a new version for every package.

A routine change needs no manifest version bump. To release, merge the release PR into
`main` and push the QDash `vX.Y.Z` tag; follow the repository's
[pre-push procedure](../development-flow.md#before-pushing), including `task check`.
The versioning script rejects malformed tags and tags older than a known QDash release.

Consumers install packages with:

```bash
pi install npm:@oqtopus-team/pi-qdash
pi install npm:@oqtopus-team/pi-qcaleval
```

For existing standalone pi installations, remove the old `@orangekame3/pi-qcaleval`
extension before installing the new name to avoid duplicate tools. Existing QDash
evaluation records retain the original evaluator name and remain readable.

Append `@beta` to select the prerelease channel. The packed artifacts contain the
extension source, bundled skills, README, and license; they have no workspace-only
dependencies.

## Publishing configuration

Configure [npm Trusted Publishing](https://docs.npmjs.com/trusted-publishers/) for
both pi packages with organization `oqtopus-team`, repository `qdash`, and
workflow filename `publish-typescript-packages.yml`. Configure the same
workflow for `@oqtopus-team/qdash-client` and `@oqtopus-team/qdash-sdk`. All four packages publish from a
GitHub-hosted runner with OIDC and no npm token. npm validates the calling workflow,
not the reusable `publish-qdash-typescript-client.yml` that runs `npm publish`, so
`publish-typescript-packages.yml` is the only workflow filename to authorize. This
package-owner setting is external to the repository; merging the workflow alone does
not authorize publishing. `@oqtopus-team/qdash-sdk` is a new npm package: until a
maintainer of the `oqtopus-team` scope creates it and adds this trusted publisher, the
`publish-sdk` job fails on `develop` and on QDash tags, and neither pi package publishes.
Enable **Allow npm publish** for the trusted publisher because this workflow publishes
directly rather than staging releases. A new publisher configuration must complete its
first successful publish within two days; otherwise, recreate the expired configuration.

[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) for `qdash-client`
stays registered for workflow filename `publish-qdash-client.yml`. `qdash-sdk` needs its own
PyPI publisher before its first release: owner `oqtopus-team`, repository `qdash`, workflow
filename `publish-qdash-client.yml`, and no environment, matching the `publish-sdk` job.
A maintainer adds it on PyPI as a pending publisher, because the project does not exist yet;
until then that job fails after `qdash-client` publishes. PyPI does not support
reusable workflows as trusted publishers, so that workflow remains top-level and receives
the version through `workflow_run` instead of being called by this workflow. PyPI then
sees `publish-qdash-client.yml` on the default branch, `develop`, for every publication.

## Retiring the original repositories

Keep the original repositories available until a QDash beta and stable release
of each package have published successfully and install correctly in standalone
pi. During the pi-qdash handover, avoid publishing from both repositories
concurrently, so its old workflow cannot overwrite the npm dist-tags. After verifying the new
release path, disable the old publish workflows, update their README links to
QDash, and archive them. Preserve the existing npm packages and versions.

Each package's `UPSTREAM.md` records the imported repository and commit. Its
original license and changelog remain alongside the source; the historical
repositories retain the earlier commit and release history.
