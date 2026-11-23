# Documentation Guidelines

Write the shortest page that lets its reader complete the task or make the change.

## Readers and Sections

| Section | Purpose |
| --- | --- |
| `user-guide/` | Set up, operate, and use QDash |
| `developer-guide/` | Understand, change, and test the code |
| `reference/` | Look up settings, APIs, and data models |

Give each page one audience and one purpose. Link to another page instead of repeating it.
Keep setup and operations in the User Guide, implementation details in the Developer Guide.

## Writing for Users

Start with when to use the feature, then numbered steps. Use the exact **page** and **button**
names. Keep only decisions and caveats that change what the reader should do.

Leave out internal files, storage keys, and UI edge cases. Commands belong in setup and operations;
workflow code and client examples are appropriate when the reader must write them.

## Writing for Developers

State what the component owns, its essential rules and why they matter, where to change it,
and how to test it. Link to source for exhaustive implementation detail.
Do not narrate every branch, field, or test. Keep component tests with their component.

## Reference Pages

Use compact tables for settings and contracts. Keep required values, defaults, and limits.
Link to generated APIs or source schemas instead of maintaining a second copy.

## Every Page

- Start with a short title and a direct context sentence.
- Use short sentences, active voice, and one term for each concept.
- Show one useful example. Keep prerequisites and failure recovery next to the relevant step.
- Use headings for questions readers need answered, without numbered prefixes.
- Remove manual contents, summaries, roadmaps, empty checklists, and generic advice.
- Link related material where it is needed, without a separate list of repeated links.
- Aim for 40–100 lines. Longer setup procedures or references are fine when the extra detail is necessary.

### Diagrams and Media

Add a diagram only when it makes a relationship easier to understand. Use Mermaid for small
flows or `<Diagram name="..." caption="..." />` with SVGs in `docs/diagrams/`.
SVGs use VitePress theme colors, `role="img"`, a descriptive `aria-label`, and unique marker IDs.

Use screenshots or short GIFs when readers need to recognize a screen or follow an interaction.
Store them in `docs/public/images/guides/`; use representative, non-sensitive data and meaningful
alt text. The text must remain useful without the media. Do not publish empty placeholders.

## Checks

Verify commands, labels, defaults, and paths against the code. Preserve useful incoming anchors
when shortening a page. Never remove backup, access-control, hardware, or migration requirements
just to meet a length target.

```bash
task build-docs
task check-docs-links
```

After Mermaid changes, also run `task check-docs-mermaid`; the build alone does not parse diagrams.
Use `#59;` for semicolons in sequence messages. `task dev-local-setup` installs the link checker.

## Sidebar

Keep User Guide and Developer Guide as the main groups, with Reference under Developer Guide.
Order pages by the reader's task; collapse specialist groups. Each page needs a sidebar entry
in `docs/.vitepress/config.mts`. When moving a page, add its old path to
`docs/.vitepress/theme/redirects.ts`.

## Exceptions

Do not restructure machine-consumed task-knowledge templates. Community policies
(`CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`) follow GitHub conventions.
