# Documentation Guidelines

Rules for writing and maintaining documentation in QDash.

## Structure

**Title** — Use a short descriptive title. Don't append "for QDash" or "Documentation".

```markdown
# API Design Guidelines        ← Good
# API Design Guidelines for QDash  ← Redundant
```

**Opening** — Start with one sentence of context, then dive into content. Don't write "This document describes/defines/explains...".

```markdown
# Logging

The API uses structured JSON logging with request ID correlation.

## Configuration
...
```

**No Table of Contents** — The docs site generates navigation automatically. Manual TOC sections get stale and add noise.

**No Summary sections** — If the document is well-structured, a summary just restates what's already written. End when the content ends.

## Content

**Be direct** — State facts and conventions. Avoid hedging ("you might want to consider...") and filler ("it is important to note that...").

**No checklists** (`- [ ]`) — Empty checkbox lists are not actionable in markdown docs. If something is a rule, state it as a rule. If it's a CI step, it belongs in CI configuration.

**No "Future Enhancements"** — Track planned work in GitHub Issues, not in docs.

**No "Best Practices" / "Quick Reference" appendices** — Integrate guidance where it's relevant. A separate "best practices" section at the end usually restates the preceding content.

**No "Related Documentation" padding** — Link inline where relevant instead of collecting links at the bottom. Exception: "Implementation Files" or "References" listing source file paths are useful.

## Formatting

**Section headings** — Use descriptive names. Avoid numbered prefixes ("1. Overview", "2. Architecture") since the site handles ordering.

**Code examples** — Show the pattern once with good/bad contrast. Don't repeat the same pattern in different sections.

**Tables** — Use for structured data (API endpoints, configuration options, file mappings). Don't use for prose that could be a paragraph.

**Emoji** — Don't use emoji in docs. Use plain text for status indicators in tables (Yes/No instead of checkmark emoji).

## Exceptions

**task-knowledge files** (`docs/task-knowledge/`) have a fixed template structure consumed by the copilot system prompt. Don't restructure these.

**Architecture docs** with "References" sections listing implementation file paths — these are useful for navigating from docs to code.
