# qdash-sdk

`qdash-sdk` provides `qdash.sdk`: the `QDash` session and calibration pipeline definitions
built on [`qdash-client`](../../clients/python/README.md). Installing it installs the matching
`qdash-client` release:

```bash
pip install qdash-sdk
```

The [Python client guide](../../docs/reference/clients/python.md) covers configuration and the
pipeline API.

## Develop the Package

Install the workspace and run the SDK checks from the repository root:

```bash
uv sync --all-groups --all-packages
task test-sdk
```

`src/qdash/sdk/` holds the SDK sources; API requests, models, configuration, and errors stay in
`qdash-client`. `tests/test_sdk_distributions.py` builds both wheels and checks that each one
installs only its own namespace.

## Version and Publication

`qdash-sdk` has no version of its own. hatch-vcs derives it the same way as `qdash-client`,
and `hatch_build.py` pins the dependency to that version: a build of `X.Y.Z` or `X.Y.ZbN`
requires `qdash-client==X.Y.Z` or `qdash-client==X.Y.ZbN`. Development builds require any
`qdash-client`.

`.github/workflows/publish-qdash-client.yml` publishes both packages from one release record:
`qdash-client` first, then `qdash-sdk`. See
[Python SDK architecture](../../docs/developer-guide/architecture/python-sdk.md#packaging-and-release).
