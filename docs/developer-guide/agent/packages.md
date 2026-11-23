# Pi Packages

QDash's root Bun workspace builds two independently published pi extensions alongside the runtime,
TypeScript client, and SDK.

| Source | Package |
| --- | --- |
| `packages/pi-qdash/` | `@oqtopus-team/pi-qdash` |
| `packages/pi-qcaleval/` | `@oqtopus-team/pi-qcaleval` |

## Development

Use the [development toolchain](../setup.md), then install from the repository root with Bun 1.4.0;
package tests require Node.js 24.

```bash
bun install --frozen-lockfile
task ci-pi-packages
task ci-agent-runtime
```

Use the root `bun.lock`, not package-local lockfiles. Both checks build the client and SDK first.
For direct pi CLI use, run `task build-client-ts` first. Rebuild `agent-runtime` after extension
or skill changes. [Pi Extension Design](./extensions.md) explains the shared-host boundary.

## Distribution

`.github/workflows/publish-typescript-packages.yml` owns the release sequence:
client → TypeScript SDK → pi packages. Its verified release record supplies the Python client
and SDK versions to `publish-qdash-client.yml`.

| Trigger | Result |
| --- | --- |
| Pull request | Validate and pack; no publication |
| Push to `develop` | Publish beta packages |
| QDash `vX.Y.Z` tag | Publish all six packages as `X.Y.Z` |
| Manual branch run | Validate only |
| Manual tag run | Retry the stable release |

No package-specific tag or routine manifest bump is needed. Packed dependencies use exact release
versions instead of `workspace:*`. Beta pi packages use a run/attempt suffix; they pin the client
version from the same run.

The Python publication validates the originating workflow, commit, ref, and release record before
running that commit's code. Stable tags must resolve to a commit on `main`; beta commits must be
on `develop`. Keep release tags and branches protected.

Publication is not atomic across registries. Rerun failed jobs to recover; existing stable versions
are skipped and an older tag cannot move `latest` backward. Follow the
[pre-push procedure](../development-flow.md#before-pushing), including the full check gate.

## Publishing configuration

Configure Trusted Publishing for organization `oqtopus-team`, repository `qdash`:

| Registry | Packages | Authorized workflow |
| --- | --- | --- |
| npm | Client, SDK, both pi packages | `publish-typescript-packages.yml` |
| PyPI | `qdash-client`, `qdash-sdk` | `publish-qdash-client.yml` |

Authorize the calling npm workflow, not the reusable client workflow. Enable direct npm publishing.
Create new packages/pending publishers before release; repository configuration alone does not
grant registry access. These jobs use OIDC, not stored publication tokens.

## Retiring the original repositories

Verify beta and stable installs before disabling old publishers or archiving repositories.
Do not publish the same package concurrently from both repositories. Preserve existing versions,
licenses, changelogs, and each package's `UPSTREAM.md`.

Standalone users moving to `@oqtopus-team/pi-qcaleval` should remove the old
`@orangekame3/pi-qcaleval` extension first to avoid duplicate tools.
