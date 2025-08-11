---
description: Generate a commit message based on current git changes
allowed-tools:
  - Bash
---

Based on the current git changes, generate an appropriate conventional commit message following these rules:

1. Use conventional commit format: `type(scope): description`
2. Types: feat, fix, docs, style, refactor, test, chore
3. Scope should be: ui, api, workflow, scripts, config, etc.
4. Description should be concise and specific

First, analyze the changes:
!git status --short
!git diff HEAD --stat

Then provide:

1. A suggested commit message
2. The git command to commit with that message

Focus on:

- What files were changed
- What the main purpose of the change is
- Whether it's a fix, feature, or other type of change

$ARGUMENTS
