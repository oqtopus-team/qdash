# QDash Project Reference Guide

## Quick Reference

- **Repository**: https://github.com/oqtopus-team/qdash
- **Documentation**: https://oqtopus-team.github.io/qdash/
- **License**: Apache 2.0

## Project Overview

QDash is a web platform for managing and monitoring qubit calibration workflows. It provides an interface to manage calibration processes, track observational data, and configure calibration parameters.

## Architecture

See [docs/developer-guide/architecture.md](docs/developer-guide/architecture.md) for detailed architecture documentation.

| Component       | Location               | Technology                                      |
| --------------- | ---------------------- | ----------------------------------------------- |
| Frontend (UI)   | `/ui/`                 | Next.js 14, TypeScript, DaisyUI, TanStack Query |
| Backend (API)   | `/src/qdash/api/`      | FastAPI, Python 3.11-3.12, MongoDB, PostgreSQL  |
| Workflow Engine | `/src/qdash/workflow/` | Prefect 3, qubex                                |

## Directory Structure

```
qdash/
├── ui/                      # Frontend (see docs/developer-guide/ui/)
├── src/qdash/
│   ├── api/                 # Backend API (see docs/developer-guide/api/)
│   └── workflow/            # Workflow engine (see docs/developer-guide/workflow/)
├── docs/                    # Documentation
├── tests/                   # Test files
└── config/                  # Configuration files
```

## Development Quick Start

```bash
# Frontend (in /ui/)
bun install && bun run dev

# Backend (from project root)
uvicorn src.qdash.api.main:app --reload

# Generate API client
task generate
```

For detailed setup instructions, see [docs/developer-guide/setup.md](docs/developer-guide/setup.md).

## Key Documentation

| Topic              | Location                                                                     |
| ------------------ | ---------------------------------------------------------------------------- |
| UI Guidelines      | [docs/developer-guide/ui/guidelines.md](docs/developer-guide/ui/guidelines.md)       |
| UI Architecture    | [docs/developer-guide/ui/architecture.md](docs/developer-guide/ui/architecture.md)   |
| API Design         | [docs/developer-guide/api/design.md](docs/developer-guide/api/design.md)             |
| Development Flow   | [docs/developer-guide/development-flow.md](docs/developer-guide/development-flow.md) |
| Database Structure | [docs/reference/database-structure.md](docs/reference/database-structure.md) |
| Database Indexes   | [docs/reference/database-indexes.md](docs/reference/database-indexes.md)     |
| Notes Architecture | [docs/developer-guide/architecture/notes.md](docs/developer-guide/architecture/notes.md)                     |
| Copilot Knowledge  | [docs/developer-guide/copilot/knowledge-layout.md](docs/developer-guide/copilot/knowledge-layout.md) |
| Dashboard Guide    | [docs/user-guide/dashboard.md](docs/user-guide/dashboard.md)                 |
| Cryo Guide         | [docs/user-guide/cryostats-and-cool-downs.md](docs/user-guide/cryostats-and-cool-downs.md)                           |
| Docs Guidelines    | [docs/developer-guide/docs-guidelines.md](docs/developer-guide/docs-guidelines.md)   |

## Claude Code Custom Commands

| Command           | Description                                           |
| ----------------- | ----------------------------------------------------- |
| `/commit`         | Analyze changes and suggest a commit message          |
| `/suggest-commit` | Generate commit message suggestion without committing |
| `/auto-commit`    | Automatically commit with generated message           |

## Notes for AI Assistants

- **Don't edit generated code**: `ui/src/client/` and `ui/src/schemas/` are auto-generated from OpenAPI
- **Regenerate after API changes**: Run `task generate` when backend API changes
- **Follow existing patterns**: Check `docs/developer-guide/ui/guidelines.md` for coding standards
- **Follow docs guidelines**: Check `docs/developer-guide/docs-guidelines.md` when writing documentation. Use the shared `technical-docs` skill to write, verify and review a page, and the shared `document-changes` skill to audit code changes for documentation impact (`.agents/skills/` is the source; `.claude/skills/` links to it)
- **Use conventional commits**: See `docs/developer-guide/development-flow.md`

## Useful Links

- [DeepWiki](https://deepwiki.com/oqtopus-team/qdash) - AI-powered codebase exploration
- [Issue Tracker](https://github.com/oqtopus-team/qdash/issues)
- [Slack Channel](https://oqtopus.slack.com/archives/C08KM5JPUEL)
