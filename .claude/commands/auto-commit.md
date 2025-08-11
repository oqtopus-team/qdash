---
description: Automatically commit with generated message (no Claude signature)
allowed-tools:
  - Bash
---

I'll analyze your changes and create an appropriate commit message without Claude Code signature, then commit them for you.

Analyzing changes...
!git status --short
!git diff HEAD --stat

Based on these changes, I'll:

1. Generate an appropriate conventional commit message
2. Stage all changes
3. Commit with the generated message (without Claude signature)

The commit will follow the format:

- `feat(scope):` for new features
- `fix(scope):` for bug fixes
- `docs:` for documentation changes
- `style:` for formatting changes
- `refactor:` for code refactoring
- `test:` for test changes
- `chore:` for maintenance tasks

Note: This command will NOT include Claude Code signature in commit messages.

$ARGUMENTS
