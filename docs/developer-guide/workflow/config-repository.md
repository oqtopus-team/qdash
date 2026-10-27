# Configuration Repository

`ConfigRepository` is the one place that pulls, commits, pushes and proposes changes to the Qubex
configuration tree. Every writer, the calibration session, the manual parameter edit, the chip
provisioning services and the **Config** page, goes through it, so one set of rules decides
which files a caller may touch and how the local tree relates to the remote.

## Responsibility Boundaries

| Component | Owns | Does not own |
| --- | --- | --- |
| `ConfigRepository` (`src/qdash/common/infrastructure/config_repository.py`) | Mode detection, git operations on the root, pull request creation | Deciding what to write, YAML content, file locks of individual parameter files |
| `QubexLayout` | Where files live (`config/`, `params/<system_id>/`, `calibration/<system_id>/`) | Synchronization |
| `GitHubIntegration` (`src/qdash/workflow/service/github.py`) | Which files a session publishes, writing the master note into each System's directory | Git |
| `CalibrationGitHubService` | Publishing a manual edit under the same file locks the YAML writer holds | Git |
| `FileService` | The **Config** page: status, pull with hooks, pull request of the changed files | Git |

## Modes

The mode is decided once per instance from the environment and the root:

| Mode | Condition | `pull` | `publish_owned` | `upsert_shared` | `propose` |
| --- | --- | --- | --- | --- | --- |
| `github` | `CONFIG_REPO_URL`, `GITHUB_USER`, `GITHUB_TOKEN` set | Publish unpushed owned files, then `reset --hard origin/<branch>`; refuse while other files are dirty | Commit the given paths in the root and push, rebasing on rejection | Edit a fresh clone and push, retried from scratch up to three times, then pull the root | Branch and pull request holding only the given paths |
| `local-git` | `.git` exists, a value missing | Nothing | Local commit | Local commit | Local commit |
| `plain` | Neither | Nothing | Change-log row | Write the file, change-log row | Change-log row |

`GitHubSettings.from_env` also reads `workflow.github.branch` and `workflow.github.review_required`
from `config/app/workflow.yaml`. With `review_required`, `publish_owned` in `github` mode calls
`propose` instead of pushing, and the result carries the pull request URL.

## Owned and Shared Files

A path is **owned** when it sits under a System's `params/` or `calibration/` directory
(`params/<system_id>/...` in the shared layout, `<chip_id>/params/...` in the legacy layout). A
path is **shared** when it is one of `config/{chip,system,wiring,box,skew}.yaml`.

- `publish_owned` accepts owned paths only and raises `ValueError` otherwise, so an automated
  workflow cannot push a hardware catalog by accident.
- `upsert_shared` edits whole top-level keys of shared files (`{"system.yaml": {"chip-1-quel3":
  {...}}}`; `None` removes a key) and keeps every other key and comment. It works from a fresh
  clone so a stale local root never overwrites entries another QDash instance added.
- `propose` takes any path; `.git`, `*.lock` and `*.tmp` are always left out.
- A repository built over a plain `Path` (no `QubexLayout`) has no owned files; every dirty file
  then blocks a pull.

## Invariants

- **A publish never resets the working tree.** `publish_owned` stages exactly the given paths,
  commits in the root and pushes; a rejected push is rebased with `--autostash`. Parameter values
  another session has written but not yet published survive. The former `_sync_local_repo`
  (`reset --hard` after every push) is gone for this reason.
- **A pull publishes before it resets.** Dirty owned files are committed and pushed first, so
  `reset --hard` cannot discard calibration results. Dirty shared files stop the pull with
  `DirtySharedFiles` unless `force`.
- **Git operations on one root are serialized** with a `filelock.FileLock` kept inside `.git`
  (`.qdash-repository.lock`), so a session and the **Config** page cannot interleave commits.
- **Credentials never reach `.git/config` or an error message.** Git receives a one-shot
  credential helper through `GIT_CONFIG_*` environment variables, the remote URL stays plain, and
  every raised `ConfigRepositoryError` masks the token.
- **Every write is observable.** `publish_owned`, `upsert_shared` and `propose` report the
  chip, paths, actor, mode and commit to the repository's `ChangeLogSink`. The default sink keeps
  nothing (git history is the record); tests pass a recording sink, and a `plain`-mode deployment
  that wants a database history can plug one in. A failing sink never undoes the write.

## Callers

| Caller | Call | When |
| --- | --- | --- |
| `Orchestrator._pull_github_config` via `GitHubIntegration.pull_config` | `pull()` | Session start when `enable_github_pull`; a refused pull is logged and the session uses the local files |
| `CalibService._push_to_github_if_configured` via `GitHubIntegration.push_files` | `publish_owned([calib_note of each used System, params files])` | Session finish; the Systems come from the execution note `system_ids` |
| `CalibrationGitHubService.sync` | `publish_owned` | Manual parameter edit and its retry |
| `agent_candidate_apply` | `pull()` then `publish_owned` through `GitHubIntegration` | Applying an agent candidate to the backend |
| `FileService.git_pull_config` / `git_push_config` | `sync(force)` / `propose(dirty paths)` | **Config** page |
| `ConfigRepositoryService` | `status()` / `sync()` | `GET /config/repository/status`, `POST /config/repository/sync` |
| Prefect tasks `pull_github`, `push_github` | `pull()` / `publish_owned` | Thin wrappers for Python flows |

`GitHubPushConfig.file_types` lists what a session publishes: `CALIB_NOTE` writes the project's
master note into `calibration/<system_id>/calib_note.json` of every used System, `ALL_PARAMS`
collects `params/<system_id>/*.yaml` narrowed by `params_file_names`. Both go out in one commit.
The former `PROPS` and `PARAMS` types (`props.yaml`, `params.yaml`) are gone: per-file parameter
YAML is the Qubex 1.5 format.

## Extend It

- **A new writer** builds a repository with `get_config_repository(layout, actor=username)` and
  calls `publish_owned` for System files or `upsert_shared` for catalog entries. Pass `chip_id` so
  the write is attributed to the chip.
- **Another workspace** (not the Qubex tree) passes its root `Path`, `label` (branch prefix) and a
  `GitHubSettings.from_env(repo_url_env=...)`.
- **Pull request creation** is injectable (`pull_request_creator`) for tests and for a different
  hosting API.

## Testing

| Concern | Tests |
| --- | --- |
| Modes, pull, publish, upsert, propose, retries, dirty checks, masking | `tests/qdash/common/infrastructure/test_config_repository.py` (temporary bare origin, no network) |
| Session publish per System | `tests/qdash/workflow/service/test_github_integration.py` |
| Manual edit publish and retry | `tests/qdash/api/services/test_manual_update_service.py` |
| **Config** page status, pull, pull request of changed files | `tests/qdash/api/services/test_file_service.py` |

Run `uv run pytest tests/qdash/common/infrastructure tests/qdash/api/services/test_file_service.py`
after changing git behaviour; the fixtures create real repositories under `tmp_path`.
