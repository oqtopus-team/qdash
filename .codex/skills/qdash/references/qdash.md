# QDash Notes

Use this reference when a QDash request is outside the helper's common commands or when you need to extend the helper.

## Client Configuration

Use `qdash-client` as the standard transport. It reads profiles from `$XDG_CONFIG_HOME/qdash/config.ini`, or `~/.config/qdash/config.ini` when `XDG_CONFIG_HOME` is unset. Use `QDashClient.from_profile("profile-name")` for saved profiles and `QDashClient.from_env()` for `QDASH_*` variables.

Important profile keys:

- `base_url`
- `api_token`
- `project_id`
- `cf_access_client_id`
- `cf_access_client_secret`
- `timeout_seconds`
- `retry_max_attempts`
- `retry_backoff_seconds`
- `retry_max_backoff_seconds`
- `verify_tls`
- `proxy`
- `user_agent`

Do not display secret values. If debugging config, report whether a key is present, not its value.

## Common Read-Only Commands

```bash
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local chips
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local default-chip
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local metrics-config
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local chip-metrics --chip-id chip-001
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local chip-qubits --chip-id chip-001 --limit 20
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local chip-qubit --chip-id chip-001 --qid Q00
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local chip-couplings --chip-id chip-001 --limit 20
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local chip-coupling --chip-id chip-001 --coupling-id Q00-Q01
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local timeseries --parameter t1 --qid Q00 --start-at 2026-06-01T00:00:00Z --end-at 2026-06-08T00:00:00Z
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local task-results --limit 20 --status success --chip-id chip-001
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local task-result --task-id task-001
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local task-note --task-id task-001
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local task-result-issues --task-id task-001
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local task-knowledge
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local task-knowledge --task-name t1
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local task-knowledge-markdown --task-name t1
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local qubit-latest --task t1 --chip-id chip-001
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local qubit-history --qid Q00 --task t1 --date 20260625
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local coupling-latest --task cz_error_rate
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local coupling-history --coupling-id Q00-Q01 --task cz_error_rate --date 20260625
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local projects
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local files-tree
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local file-content --path flows/demo.py
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local git-status
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local issues --limit 20 --is-closed false
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local issue-knowledge --status approved --limit 20
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local flows
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local flow-templates
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local flow-template --template-id full_calibration
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local flow-helper-files
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local flow-helper-file --filename common.py
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local executions --limit 20
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local ai-reviews --chip-id chip-001 --limit 20
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local ai-review-runs --chip-id chip-001 --limit 20
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local ai-review-run --review-run-id run-001
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local provenance-stats
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local provenance-history --parameter-name t1 --qid Q00 --limit 20
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local provenance-changes --within-hours 24 --parameter-name t1
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local raw-get --path /projects
uv run --with qdash-client python skills/qdash/scripts/qdash_query.py --profile local raw-get --path /task-results --params '{"limit": 20}'
```

For local qdash-client development, set `QDASH_REPO_PATH` to a checkout and run with client dependencies:

```bash
QDASH_REPO_PATH=~/src/github.com/oqtopus-team/qdash uv run --with httpx --with pydantic python skills/qdash/scripts/qdash_query.py --profile local chips
```

Do not use `curl` as the default transport. Use it only for explicit low-level debugging after the user asks for it; otherwise rely on `qdash-client` for profile loading, auth headers, Cloudflare Access headers, project headers, retries, and response normalization.

## OpenAPI Locations

In a local `oqtopus-team/qdash` checkout:

- `docs/oas/openapi.json`: machine-readable OpenAPI spec.
- `docs/reference/openapi.md`: VitePress page that renders the OpenAPI viewer.
- `src/qdash/api/routers/`: FastAPI routers for endpoint behavior.
- `src/qdash/api/schemas/`: response and request schemas.
- `src/qdash/client/services/client.py`: current high-level `qdash-client` methods.

Useful path groups from the OpenAPI spec:

- `/chips`, `/chips/{chip_id}`, `/chips/{chip_id}/qubits`, `/chips/{chip_id}/couplings`
- `/metrics/config`, `/metrics/chips/{chip_id}/metrics`, `/metrics/chips/{chip_id}/qubits/{qid}/history`
- `/task-results`, `/tasks/{task_id}/result`, `/task-results/{task_id}/note`, `/task-results/{task_id}/issues`, `/task-results/timeseries`, `/task-results/qubits/latest`, `/task-results/couplings/latest`, `/task-results/ai-review`
- `/tasks`, `/task-knowledge`, `/tasks/{task_name}/knowledge`, `/tasks/{task_name}/knowledge/markdown`
- `/projects`, `/provenance/*`, `/issues`, `/issue-knowledge`, `/forum/posts`
- `/flows/*`, `/flows/templates`, `/flows/helpers`, `/executions/*`, `/files/*`, `/admin/*`

Named helper commands cover common read-only paths. Use `raw-get` only for read-only endpoints that are not yet first-class commands. Treat these as operationally sensitive even if the HTTP method is GET: `/files/git/pull`, `/files/git/push`, `/flows/{name}/execute`, `/executions/{id}/re-execute`, `/task-results/{id}/exclude`, admin endpoints, auth endpoints, and membership changes.

Use `jq` to inspect methods and parameters:

```bash
jq '.paths["/task-results/timeseries"]' ~/src/github.com/oqtopus-team/qdash/docs/oas/openapi.json
jq -r '.paths | keys[]' ~/src/github.com/oqtopus-team/qdash/docs/oas/openapi.json
```

## Extending the Helper

Prefer adding a named command to `scripts/qdash_query.py` when an operation is likely to be reused. Keep commands read-only by default and implemented through `qdash-client`. For write operations, require an explicit flag such as `--confirm-write` and make the calling agent ask the user first.

When adding a read-only command:

- Reuse `client_get()` when the command maps directly to one GET endpoint.
- Default `--chip-id` to `get_default_chip_id()` only when the endpoint requires a chip and that behavior is useful for dashboards.
- Keep pagination options explicit as `--skip` and `--limit`.
- Accept ISO datetimes for API date-time fields and `YYYYMMDD` for task-result history date fields.
- Return JSON with `status_code` and `data` for raw endpoint wrappers; return model JSON for high-level `qdash-client` methods.
