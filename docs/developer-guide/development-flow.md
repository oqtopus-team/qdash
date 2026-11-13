# Development Flow

Develop changes on branches from `develop`; release from `main`.

## Branch Strategy

Create feature, bug-fix, and hotfix branches from `develop`, which contains the latest merged code.

<Diagram name="development-flow" caption="Work branches off develop and returns by squash-merged PR; releases go from develop to main through the release PR and a version tag." />

### Branch Naming

Use `feature/<topic>`, `bugfix/<topic>`, or `hotfix/<topic>`.

## Conventional Commits

Use `<type>(<scope>): <summary>` with a short English summary and no trailing period, following
[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Use `api`, `workflow`,
`ui`, `docs`, `infra`, or `repo` as the scope when applicable.

### Commit Message Format

Enable the repository template locally:

```bash
git config --local commit.template .gitmessage
```

The template opens in your Git editor when you commit. For example:

```text
docs(docs): simplify workflow authoring guide
```

On the host, commit with `nix develop -c git commit` so hooks use the pinned scanner; see
[Before Pushing](#before-pushing).

## Correspondence between Commit Messages and Labels

When creating a PR to the `main` branch, labels are automatically assigned based on the commit messages.
Below is the correspondence between prefixes and labels:

| Prefix | Label | Description |
| --- | --- | --- |
| feat: | `feature` | Adding a new feature |
| fix: | `bugfix` | Bug fixes |
| docs: | `documentation` | Documentation only changes |
| style: | `style` | Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc) |
| refactor: | `refactor` | Code changes that neither fix a bug nor add a feature |
| test: | `test` | Adding or correcting existing tests |
| ci: | `ci` | Adding or updating CI configuration and scripts |
| chore: | `chore` | Minor changes or maintenance tasks |

## Secret Scanning

Betterleaks runs on every commit via a Lefthook-managed pre-commit hook and blocks the commit on any finding. Trufflehog scans git history in CI for verified leaks. See [Credential Scanning](./conventions/credential-scan.md) for tool roles, output reading, and false-positive handling.

`task check` includes the local leak scan. See
[Credential Scanning](./conventions/credential-scan.md#running-locally) for scan commands,
file coverage, and target-branch configuration.

## Pull Requests

Open pull requests against `develop` unless the release process requires another base branch.
Use the repository pull request template and keep the description focused on the behavior change,
important implementation notes, and verification performed.

### Before Pushing

Every push requires a successful `task check` on the content being pushed, including
documentation-only changes and updates to existing PRs. Focused tests during development,
pre-commit hooks, and CI supplement this gate.

On the host, run `task check` and commits inside the Nix shell, which provides the
pinned Betterleaks release. In the DevContainer, run the same commands directly.
`task check` first runs `task check-betterleaks-version` and stops if the `betterleaks`
on `PATH` is a different release; see
[scanner version](./conventions/credential-scan.md#scanner-version).

Stage intended new files so the leak scan includes them. Fetch the PR target branch
to refresh its local reference, then run the check from the repository root:

```bash
git fetch origin develop
nix develop -c task check
```

For a different PR target, fetch that branch and set `LEAKS_BASE`, for example:

```bash
git fetch origin main
nix develop -c task check LEAKS_BASE=origin/main
```

Commit with `nix develop -c git commit` so the pre-commit hook uses the same scanner.

`task check` runs auto-fixing linters. Review the resulting diff and include intended
fixes in the commit. If you edit files after the check, rerun it before pushing.
Require exit status 0; if the check fails or cannot run, resolve the failure before
pushing. Report the failed command and reason if blocked, and do not push.

Record the check command and result in the PR description and the agent's final handoff.
