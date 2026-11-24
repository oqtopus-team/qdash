# Development Flow

Branch from `develop`, test your change, and open a pull request back to `develop`.
Releases go from `develop` to `main`.

## Branch Strategy

Use `feature/<topic>`, `bugfix/<topic>`, or `hotfix/<topic>`. From a clean checkout:

```bash
git fetch origin develop
git switch -c feature/your-topic origin/develop
```

If the checkout has work in progress, commit or stash it before switching branches.

<a id="commit-message-format"></a>

## Conventional Commits

Write `<type>(<scope>): <summary>` with a short English summary and no trailing period:

```text
docs(docs): simplify workflow authoring guide
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `ci`, `chore`.
Scopes: `api`, `workflow`, `ui`, `docs`, `infra`, or `repo` when applicable.
Set the optional template with `git config --local commit.template .gitmessage`.

## Pull Requests

Use `.github/pull_request_template.md`. Describe the problem, changed behavior, and verification.
Keep the PR focused on one change. After the check below passes, stage and review the intended
diff, commit inside Nix or the DevContainer, and push your branch. On GitHub, choose `develop`
as the PR base. Contributors without repository write access push to their own fork instead.
A submitted PR should show the intended files and a recorded successful check command.

### Before Pushing

Every push requires a successful full `task check`, including docs-only changes and PR updates.
Focused tests and CI do not replace this gate.

`task check` completes auto-fixes before running independent checks in parallel, then runs
the leak scan after those checks pass. Output is grouped by task, so long-running tests can
remain silent until they finish. For focused troubleshooting, `task check-lanes` runs only
the parallel checks; it does not replace the full pre-push check.

Local checks run the full Python test suite without coverage instrumentation. CI collects
coverage with `task ci-test`; run that task locally when you need a coverage report.

1. Stage intended new files so the leak scan includes them.
2. Fetch the PR target and run the checks from the repository root:

   ```bash
   git fetch origin develop
   nix develop -c task check
   ```

   For another target, fetch it and set `LEAKS_BASE`, for example:

   ```bash
   git fetch origin main
   nix develop -c task check LEAKS_BASE=origin/main
   ```

3. Review auto-fixes and include intended changes. If you edit afterward, rerun the check.
4. Require exit status 0 before pushing. Fix failures; never bypass them.
5. Record the command and result in the PR and handoff.

## Secret Scanning

On the host, run checks and commits inside Nix (`nix develop -c git commit`). Inside the
DevContainer, run them directly. Both provide the pinned Betterleaks release required by the
pre-commit hook. See [Credential Scanning](./conventions/credential-scan.md) for failures and findings.
