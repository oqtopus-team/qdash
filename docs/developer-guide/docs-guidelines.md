# Documentation Guidelines

QDash documentation is written for two readers: people who use QDash and people who change
its code. Every page belongs to one of them, lives in that reader's section, and is written the
way that reader works.

## Readers and Sections

| Section | Directory | Reader | What they come for |
| --- | --- | --- | --- |
| User Guide | `docs/user-guide/` | Sets up, runs, and uses QDash: lab members, experimenters, whoever keeps the deployment running | How to get something done in the application |
| Developer Guide | `docs/developer-guide/` | Changes QDash code | How the system is built, where things live, how to extend and test them |
| Reference | `docs/reference/` | Either, when they need a fact | Tables and generated material: database collections, OpenAPI, client packages |

Setting up and operating QDash belongs to the User Guide. In a lab the people who deploy
QDash are the people who use it, and a setup page reads the same way as any other procedure.

A page serves one reader. When a topic needs both a procedure and an explanation of the
mechanism behind it, write two pages, one in each section, and link them in one line.

## Layout

```
docs/
  index.md                 Two entry points: User Guide, Developer Guide
  user-guide/
    index.md               Reading order: set up, operate, work with calibrations
    setup.md               Clone, configure, start, sign in
    operations.md          Start, stop, logs, recovery
    system-updates.md      Apply a stable release from the host
    migrations/            Steps for upgrades that change stored data
    application-tour.md    One page per job after that: running calibrations,
    ...                    reviewing results, copilot, projects, cryo, ...
  developer-guide/
    index.md               Reading order: setup, codebase, commands, testing
    setup.md  codebase.md  commands.md  testing.md  development-flow.md
    docs-guidelines.md     This page
    conventions/           Rules that apply across the code: datetime, logging,
                           qid validation, credential scanning
    api/  ui/  workflow/  copilot/
                           One directory per component: design, architecture,
                           testing, and the component's own deep dives
    architecture/          Cross-component design: schedulers, topology,
                           provenance, notes, agent platform
  reference/
    database-structure.md  Overview, collections, data flow
    data-models.md  database-documents-*.md  database-indexes.md  openapi.md
    clients/               Python and TypeScript client packages
```

Name files by topic (`reviewing-results.md`), not by audience or form (`user-...`,
`...-overview`). Every page is linked from the sidebar in `docs/.vitepress/config.mts`; a page
that is not worth a sidebar entry is not worth keeping.

## Writing for Users

A user page answers "how do I ...?" for one job: run a calibration, review results, set up a
cryostat. Start each section with when to use it, then give the steps.

- **Name what the person sees.** Page and button names in bold, as the application shows them:
  **Chip page → Evaluate**, **Settings → Copilot**. Describe what happens as a result, not how
  it is implemented.
- **Steps are numbered** when order matters; otherwise a short paragraph. One action per step.
- **Settings go in a table**: name, meaning, default. Environment variables and commands appear
  only on setup and operations pages.
- **Limits and caveats sit next to the feature** they limit, in a sentence, not in a separate
  section.
- **No internals.** No file paths, collection names, library or model names, JSON keys, HTTP
  routes, or component names. A reader who wants the mechanism gets one line: "How this works:
  [Copilot architecture](./copilot/architecture.md)."
- **No roles the application does not show.** Say "project editors" when the application calls
  them that; do not invent personas.

```markdown
## Request an AI evaluation                       ← a job, in the user's words

Open **Chip page → Evaluate** to judge the latest result of the selected task for
every qubit on the chip. Untick qubits under **Targets** to narrow the run.

The evaluation model reads the task's reference from **Knowledge**; keep that
current. How this works: [Copilot architecture](./copilot/architecture.md).
```

```markdown
## Evaluation                                      ← not a user page

The runtime asks `qcal_evaluate` the six questions in separate calls; the API
derives `missing_keys` over the questions asked on every read ...
```

## Writing for Developers

A developer page explains one responsibility: a component, a convention, a design decision.
State what it is responsible for, where the code is, what must stay true, and how to change
and test it.

- **Open with the responsibility boundary**: what this part owns and what it leaves to others.
- **Name files and symbols** the reader will open: `src/qdash/api/services/evaluation_service.py`,
  `recordFromDetails`. A **References** or **Implementation Files** list at the end is welcome.
- **Write the invariants and the reasons.** "Records are derived on every read so older
  documents are judged the same way" is worth more than a restatement of the code.
- **Show how to extend it**: add a task, add a tool, add a route, with the files touched and the
  tests to run.
- **Testing lives with the component**: each component directory has its own testing page;
  `developer-guide/testing.md` only says which to run when.
- **No procedures users already have.** Link the user page instead of repeating the steps.
- **No roadmap.** Planned work, open questions, and "phases" belong in GitHub Issues.

## Reference Pages

Reference pages are tables and generated material: collections and their fields, indexes,
the OpenAPI document, client package APIs. Keep them exhaustive and flat; explanation of why a
structure is the way it is belongs in the Developer Guide, linked from the table.

## Every Page

**Title** — A short descriptive title. Don't append "for QDash" or "Documentation".

**Opening** — One sentence of context, then the content. Don't write "This document
describes/defines/explains...".

**No Table of Contents** — The docs site generates navigation. Manual TOC sections go stale.

**No Summary sections** — End when the content ends.

**Be direct** — State facts and conventions. No hedging ("you might want to consider...") and
no filler ("it is important to note that...").

**No checklists** (`- [ ]`) — If something is a rule, state it as a rule. If it is a CI step, it
belongs in CI configuration.

**No "Future Enhancements"** — Track planned work in GitHub Issues.

**No "Best Practices" / "Quick Reference" appendices** — Integrate guidance where it is
relevant.

**No "Related Documentation" padding** — Link inline where relevant. Exception: a
**References** or **Implementation Files** list of source paths on a developer page.

**Section headings** — Descriptive names, no numbered prefixes ("1. Overview").

**Code examples** — Show the pattern once, with a good/bad contrast when that helps. Don't
repeat the same pattern in different sections.

**Tables** — For structured data (settings, endpoints, file mappings). Not for prose.

**Emoji** — None. Plain text for status in tables (Yes/No).

**Length** — A page is read in one sitting. Past roughly 400 lines, split it by topic: a testing
page by test kind, a reference by collection group.

## Checks

Documentation changes must build and keep their external links reachable. Run `task build-docs`
to validate VitePress routes and local links. Run `task check-docs-links` when Lychee is
installed to validate links and anchors against the local VitePress layout and external sites.

CI builds the documentation, checks external links in changed Markdown files, and checks every
internal link and anchor in the generated site on each pull request. A weekly scan checks every
Markdown file under `docs/` so an external page that later moves or disappears is detected
without blocking unrelated pull requests.

## Sidebar

The sidebar in `docs/.vitepress/config.mts` has two top-level groups, User Guide and Developer
Guide, with Reference under Developer Guide. Within a group, pages are in reading order: the
page a newcomer needs first comes first. When a page moves, add its old path to
`docs/.vitepress/theme/redirects.ts` so links to the old URL still arrive.

## Exceptions

**task-knowledge files** in the knowledge repository have a fixed template consumed by the
copilot system prompt. Don't restructure these.

**Community files** (`CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`) follow GitHub's
conventions, not these.
