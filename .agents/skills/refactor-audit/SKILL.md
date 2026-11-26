---
name: refactor-audit
description: >
  Find and consolidate duplicated QDash implementations while preserving caller behavior.
  Use for codebase-wide refactoring audits, shared-code extraction, or planning independently
  reviewable refactor PRs. An audit alone reports candidates; implement only when requested.
  Not needed for routine bug fixes, formatting, or documentation-impact reviews.
---

# Refactor Audit

Reduce repeated maintenance without erasing differences between callers. A smaller diff or
fewer lines is useful only when ownership and behavior remain clear.

## Map the requested scope

Read the applicable `AGENTS.md` and inspect the working tree before selecting candidates.
For a broad audit, inventory UI, API/data, workflow/common, and agent/client/SDK code; record
which areas were inspected and which were excluded. For a narrow request, stay in that area.
Exclude generated code from duplicate counts and edits. Treat independently published
packages and nested repositories as boundaries, not convenient sources of shared imports.

Use search, AST comparisons, or an available clone detector to find candidates. Inspect the
callers and existing helpers before deciding that a repeated block is redundant. Do not add
a repository dependency just to run a one-off detector. Keep a compact candidate list with
locations, intended shared owner, expected benefit, compatibility risks, and disposition.
Count new helpers and adapters when estimating savings; keep test growth separate.

QDash has source consumers as well as runtime callers. Before extracting calibration task
declarations, inspect `src/qdash/api/services/task_file_service.py`: source-parsed metadata
can disappear when literal declarations move behind an unrecognized factory. Verify the
consumer's output as well as the loaded task's values. Check package exports and build inputs
before sharing code across the pi packages, runtime, clients, or SDKs.

## Compare behavior before extraction

For each candidate, compare the original callers on the differences that matter:

- Accepted inputs, empty/missing values, defaults, and precedence between alternative fields.
- Output values, formatting, ordering, serialization, and concrete model types.
- Exception types/messages, side effects, caching, cancellation, retries, and save/rollback order.
- UI navigation, selection identity, reset triggers, loading/error states, and target-specific layout.

Use a small caller/input/expected-result table when the differences are not obvious. Preserve
distinct policies with explicit adapters or leave them separate; do not silently standardize
them as part of a refactor. Keep bug fixes outside the refactor unless they are also requested.
For example, `status ?? statusCode` differs from a numeric `statusCode` fallback, and validating
a subclass as a Pydantic base model can retain the subclass and its internal fields.

Where the boundary has meaningful risk, add characterization tests against the original
implementation first, then reuse them against the refactor. Exercise the caller's observable
result, not only the new helper. If baseline execution is impractical, state that limitation.
Use targeted checks for API schemas, source-derived metadata, or package exports when those
surfaces could change; passing ordinary tests alone does not establish their equivalence.

## Choose reviewable units before implementation

Group candidates by shared ownership and dependency, including their tests in the same unit.
Prefer units that can be reviewed, tested, and reverted independently. UI, API/data, workflow,
and agent/SDK are possible boundaries, not a fixed number of PRs. Keep unrelated small cleanups
out of a unit when they obscure its purpose. A required shared helper belongs with its callers
or in an explicit prerequisite; do not describe a dependent branch as independent.

When parallel work is authorized and useful, assign disjoint write scopes and an owner for
shared files. Include preserved behaviors and verification requirements in each brief. Keep
repository-wide auto-fixes and branch/release operations out of concurrent implementation.
This skill does not authorize delegation, pushing, or PR creation by itself.

## Verify and hand off

Review the integrated diff for differences hidden by extraction, especially caller policies
that a shared helper now controls. Run relevant focused checks and the repository's required
checks. For separate PRs, validate each branch on its actual base; a successful combined-tree
check is not evidence that every subset works. Follow `AGENTS.md` for staging, Nix, commits,
and the full pre-push gate rather than replacing them with a lighter skill-specific check.

Use the existing `document-changes` skill for documentation impact. Report inspected scope,
implemented clusters, significant deferred candidates with reasons, net production-code
change including new files, and verification limits. Distinguish source review and automated
tests from browser or hardware testing. Do not present a clone scan as an exhaustive review.
