## Pull Request title & description instructions (QDash)

Generate the Pull Request title and description for this repository (QDash).
Write in English with a professional, friendly tone. Keep it concise and scannable.

### Title
- Format: `<type>(<scope>): <summary>` (example: `fix(ui): prevent metrics page layout shift`)
- `type`: `feat|fix|docs|style|refactor|test|ci|chore`
- `scope`: use `api|workflow|ui|docs|infra|repo` when clear (omit if unclear)
- One line, no emojis
- If there is a related issue, append `(#123)` at the end

### Description
Follow the section structure in `.github/pull_request_template.md` and fill each section using bullet points.

#### Ticket
- Add the issue/ticket link or `#number` (use `N/A` if unknown)

#### Summary
- Explain what changed and why (1–2 bullets)
- Mention impact/risk and affected areas (API/Workflow/UI, compatibility, config changes)

#### Changes
- List key changes as bullets (focus on outcomes, not implementation trivia)
- For UI changes, include the screen/component name (e.g., `MetricsPageContent`)
- If OpenAPI/schema or generated client changes are involved, mention it (and whether generation was run)
