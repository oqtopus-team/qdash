---
name: technical-docs
description: >
  Write, rewrite, and review pages under docs/ in the QDash repository. Use whenever a task
  creates or edits documentation: a user-guide procedure, a developer-guide page, a reference
  table, the docs sidebar, or a review of an existing page. Applies the repository's
  two-reader policy (docs/developer-guide/docs-guidelines.md), the Google Developer
  Documentation Style Guide, and Diataxis.
---

# Technical Documentation

`docs/developer-guide/docs-guidelines.md` is the rulebook: readers, sections, layout, what every
page must and must not contain. Read it first and do not restate it here. This skill is the
working method: how to choose the page type, how to write the sentences, how to check them
against the code, and how to review before finishing.

## Pick the reader and the type

Decide both before writing a line, and keep one page to one type.

| Reader's goal | Diataxis type | QDash section | Shape |
| --- | --- | --- | --- |
| Get a job done in the application | How-to | `docs/user-guide/` | When to use it, then numbered steps; names of pages and buttons in bold; no internals |
| Set up or operate a deployment for the first time | Tutorial | `docs/user-guide/setup.md`, `operations.md` | A path that works end to end; commands the reader can paste |
| Understand how a part works or why it is built this way | Explanation | `docs/developer-guide/` | Responsibility boundary, mechanism, invariants with reasons, how to extend and test, file list |
| Look up a fact | Reference | `docs/reference/` | Flat, exhaustive tables; no narrative |

A topic that needs both a procedure and a mechanism gets two pages, one per section, linked
in one line each way (`How this works: [...]` on the user page). When a page mixes types, move
the foreign paragraphs to the page of the other type rather than smoothing them in place.

## Write

Google style, applied to this repository:

- **Lead with the answer.** The first sentence of a page or section carries its main fact. No
  "This document describes", no history of how the feature came to be.
- **One idea per sentence, active voice, present tense.** "The API derives the reference on
  every read", not "the reference will be derived by the API".
- **Define before use.** Introduce a term (record, run, reference, planner) with its meaning the
  first time; afterwards use exactly that word. Do not rotate synonyms for the same thing.
- **Concrete over abstract.** A rule shown on one real input (`Short T1 (<20 μs)` to
  `SHORT_T1`) beats a paragraph of generalities. Code and command samples must be runnable or
  taken verbatim from the code.
- **Name what the reader will open.** Developer pages name files and symbols in backticks; user
  pages name what the application shows in bold and nothing from the code.
- **Say it once.** A fact lives on one page; other pages link to it. Within a page, do not
  restate in a later section what an earlier one established.
- **Cut hedges and filler.** "Note that", "it is important to", "basically", "simply", "you
  might want to" go. State the rule or the fact.
- **Caveats next to the feature,** in a sentence, not in a separate Notes or Limitations
  section.
- **Tables for parallel structured items** (settings, questions, files, triggers), prose for
  argument. A table cell holds a phrase, not a paragraph; if cells grow past two lines, the
  content wants prose or its own section.
- **Diagrams for relationships that prose hides.** Use a small Mermaid flowchart, sequence
  diagram, state diagram, or class diagram when the reader must track at least three components,
  branches, transitions, or parallel and sequential phases. Keep labels concrete, explain the
  consequence in nearby prose, and make the surrounding text sufficient for readers who cannot
  see the diagram. Do not diagram a list, a single linear action, or the same information already
  clear in a table.
- **Keep markdown compact.** Tables use `| --- |` separators without column padding; docs are
  not run through a formatter in CI, so match the surrounding file.

## Verify against the code

A documentation claim is a claim about the code. Before a page is done:

1. Open every file and symbol the page names and confirm they exist with that name and role.
2. Check every stated behaviour (default values, limits, orderings, fallbacks, error
   handling) against the implementation or its tests, not against memory or an older page.
3. For a user page, confirm page and button labels against the UI components.
4. Resolve every relative link; a renamed or moved page needs its old path in
   `docs/.vitepress/theme/redirects.ts`.
5. A new page gets a sidebar entry in `docs/.vitepress/config.mts`, in reading order, and
   a one-line link from the page a reader would arrive from.
6. Run `bun run docs:build` in `docs/` when links or the sidebar changed; it fails on a dead
   internal link.

When a check fails, fix the page, not the code, unless the task is about the code.

## Review

Read the page once as its reader, with these questions, and rewrite until every answer is yes:

- Does the first screen tell the reader whether this is the page they need?
- Can the reader find a specific answer (a setting, a file, a step) without reading from the
  top? Headings and the first sentence of each paragraph must make that possible.
- Does each paragraph add one thing the page did not already say?
- Is the order the order the reader needs: what it is, how it behaves, how to change it, where
  the code is?
- Would a compact diagram make a multi-component relationship, branch, state change, or execution
  order faster to understand than the current prose? If so, add one and remove duplicated prose.
- Would every example run, and does every path, symbol and label exist?
- Can any sentence be deleted without losing a fact or a reason? Delete it.
- Is the page still under about 400 lines? Past that, split by topic and link.

Report what was verified against the code and what could not be verified.
