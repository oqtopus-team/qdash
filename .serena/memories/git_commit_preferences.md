# Git Commit Preferences

## Commit Message Generation Rules

1. **No Claude Attribution**: Do not include any Claude Code attribution or Co-Authored-By lines in commit messages
   - ❌ Don't include: "🤖 Generated with [Claude Code](https://claude.ai/code)"
   - ❌ Don't include: "Co-Authored-By: Claude <noreply@anthropic.com>"

2. **Use Current User**: Always use the current Git user configuration (orangekame3 / orangekame3.dev@gmail.com)

3. **Clean Commit Messages**: Generate conventional commit messages without any AI-related attribution

## Example Format

```
feat: add new feature

- Implementation detail 1
- Implementation detail 2
- Implementation detail 3
```

This preference applies to all auto-commit commands (/auto-commit, /commit, etc.)
