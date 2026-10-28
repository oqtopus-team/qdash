# Pi Packages

QDash maintains two independently published pi extensions in its root Bun workspace,
alongside `agent-runtime/`. The runtime uses the source in the checkout; npm packages
serve standalone pi CLI users.

| Directory | npm package | Stable tag |
| --- | --- | --- |
| `packages/pi-qdash/` | `@oqtopus-team/pi-qdash` | `pi-qdash/vX.Y.Z` |
| `packages/pi-qcaleval/` | `@orangekame3/pi-qcaleval` | `pi-qcaleval/vX.Y.Z` |

The Python and TypeScript clients, UI, and documentation retain their own dependency
configuration. pi-qdash keeps its explicit dependency on the published TypeScript
client, so its npm artifact works outside the monorepo. pi-qcaleval has no QDash
client or runtime dependency.

## Development

Install from the repository root with Bun 1.4.0. Package tests also require Node.js 24.

```bash
bun install --frozen-lockfile
task ci-pi-packages
task ci-agent-runtime
```

The root `bun.lock` covers the runtime and both extensions. Do not create package-local
lockfiles. Test standalone pi behavior with `pi -e ./packages/pi-qdash` or
`pi -e ./packages/pi-qcaleval` from the repository root.

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

`.github/workflows/publish-pi-packages.yml` follows the client workflows: validate
PRs, publish beta builds from `develop`, and publish stable versions from tags.
Both packages keep their existing npm names and independent version lines.

| Trigger | Result |
| --- | --- |
| PR to `develop` affecting packages, runtime, root dependencies, or release workflow | Typecheck and test both packages and runtime; upload npm tarballs without publishing |
| Push to `develop` affecting packages, root dependencies, or release workflow | Publish both tarballs with the `beta` dist-tag |
| `pi-qdash/vX.Y.Z` or `pi-qcaleval/vX.Y.Z` tag | Validate both packages, then publish only the named package as `latest` |
| Manual run on a branch | Build and validate without publishing |
| Manual run on a package tag | Retry that stable release |

Beta versions use the next patch after the highest stable tag for that package, or
its manifest version if no newer tag exists, followed by
`-beta.<GitHub run ID>.<attempt>`. QDash's `vX.Y.Z` tags do not affect package versions.
Run IDs avoid colliding with the old repositories' beta build numbers; attempts
allow a retry if one package published before the other failed.

The workflow sets the artifact version at build time, like the TypeScript client.
A routine change does not need a manifest version bump. For a stable release,
choose a version newer than the package's current npm `latest`, tag the reviewed
QDash commit with the package prefix, and push that tag. Follow the repository's
[pre-push procedure](../development-flow.md#before-pushing), including `task check`.
Do not reuse a version that npm already contains. The versioning script rejects
malformed tags and tags older than a known stable release.

Consumers continue to install packages with:

```bash
pi install npm:@oqtopus-team/pi-qdash
pi install npm:@orangekame3/pi-qcaleval
```

Append `@beta` to select the prerelease channel. The packed artifacts contain the
extension source, bundled skills, README, and license; they have no workspace-only
dependencies.

## Publishing configuration and repository retirement

Configure [npm Trusted Publishing](https://docs.npmjs.com/trusted-publishers/) for
both existing packages with organization `oqtopus-team`, repository `qdash`, and
workflow filename `publish-pi-packages.yml`. The workflow uses a GitHub-hosted
runner and OIDC rather than an npm token. This package-owner setting is external
to the repository; merging the workflow alone does not authorize publishing.

Keep the original repositories available until a QDash beta and stable release
of each package have published successfully and install correctly in standalone
pi. During the handover, avoid publishing from both repositories concurrently,
so the old workflow cannot overwrite the npm dist-tags. After verifying the new
release path, disable the old publish workflows, update their README links to
QDash, and archive them. Preserve the existing npm packages and versions.

Each package's `UPSTREAM.md` records the imported repository and commit. Its
original license and changelog remain alongside the source; the historical
repositories retain the earlier commit and release history.
