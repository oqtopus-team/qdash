---
description: Suggest a commit message without committing
allowed-tools:
  - Bash
---

I'll analyze your changes and suggest an appropriate commit message.

!git diff HEAD --name-only
!git diff HEAD --stat --stat-width=120

Based on these changes, here's my suggested commit message following conventional commits format:

$ARGUMENTS
