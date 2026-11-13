---
name: document-changes
description: >
  Audit a QDash branch, pull request, commit, or working-tree diff for documentation impact.
  Use when checking whether source changes require documentation updates or before finishing
  user-visible, API, configuration, deployment, or extension changes. Reports stale content,
  missing coverage, and broken examples; applies focused fixes only when requested. Do not use
  for a docs-only writing task, which belongs to the technical-docs skill.
---

# Document Changes

Find documentation that became inaccurate or incomplete because the code changed. Be
conservative: a documentation audit protects the public contract; it is not an opportunity to
rewrite accurate prose.

## Choose the mode

- **Report mode** is the default for an audit or review. Report findings and proposed fixes
  without editing files.
- **Edit mode** applies when the user asks to update or fix the documentation. Before editing,
  read `docs/developer-guide/docs-guidelines.md` and
  `.agents/skills/technical-docs/SKILL.md`, then make the smallest complete correction.

## Establish the change set

Use the base named by the user or the pull request. Otherwise, compare the branch with its
merge base against `develop`, then include staged and unstaged changes. Do not fetch or change
branches only to obtain a diff; state when the available local history limits the audit.

Start with `git status --short` and a name-status or stat summary before reading the full diff.
Separate source changes from generated files, tests, documentation, and repository metadata so
the public behavior is not obscured by mechanical output.

## Extract documentation-relevant changes

Look for a changed public contract:

- user-visible workflows, labels, limits, defaults, or error behavior;
- setup, deployment, upgrade, recovery, or operational commands;
- API routes, request or response schemas, and client-facing behavior;
- configuration keys, environment variables, task commands, and prerequisites;
- workflow extension points, architectural boundaries, and required test procedures.

Do not require documentation for an internal refactor, formatting-only change, test-only change,
or generated-file churn when the documented contract is unchanged. Tests can still provide
evidence for behavior described elsewhere.

## Map changes to documentation

Search `docs/`, `README.md`, and relevant community files for names, commands, routes, settings,
UI labels, and concepts found in the diff. Inspect both the current implementation and its tests
before deciding that prose is wrong. Never infer behavior from a removed line alone.

Classify each finding as:

- **Stale**: existing documentation contradicts the changed behavior.
- **Missing**: a reader cannot complete or understand a newly exposed task or contract using the
  existing documentation.
- **Broken example**: a documented command, code sample, path, symbol, label, link, or expected
  result no longer works.

Exclude generated documentation from manual edits, including `docs/oas/openapi.json`. When an
API change affects generated references, verify that the repository's generation workflow was
run instead.

## Report the result

Put actionable findings first. For each finding, give:

- the category and affected documentation path, with a line number when available;
- evidence from the changed source, test, or generated contract;
- the reader impact and the smallest suitable fix.

Distinguish a missing page from a missing paragraph. Prefer updating an existing page when it
serves the same reader goal. If there are no findings, say which public surfaces and likely
documentation locations were checked; do not return only "no changes needed."

## Apply and verify fixes

In edit mode, preserve accurate surrounding content and avoid unrelated style cleanup. Create a
page only when the change introduces a distinct reader goal that has no suitable existing home.
Keep generated files on their generation path rather than editing them by hand.

Run checks proportional to the edit. At minimum, resolve changed internal links and verify every
documented path, symbol, label, default, and example against the code. Run `task build-docs` for
documentation changes, and run `task check-docs-links` when Lychee is available and links or
anchors changed. Report any check that could not run and why.
