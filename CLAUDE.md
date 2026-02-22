# QDash Project Reference Guide

## Quick Reference

- **Repository**: https://github.com/oqtopus-team/qdash
- **Documentation**: https://oqtopus-team.github.io/qdash/
- **License**: Apache 2.0

## Project Overview

QDash is a web platform for managing and monitoring qubit calibration workflows. It provides an interface to manage calibration processes, track observational data, and configure calibration parameters.

## Architecture

See [docs/getting-started/architecture.md](docs/getting-started/architecture.md) for detailed architecture documentation.

| Component       | Location               | Technology                                      |
| --------------- | ---------------------- | ----------------------------------------------- |
| Frontend (UI)   | `/ui/`                 | Next.js 14, TypeScript, DaisyUI, TanStack Query |
| Backend (API)   | `/src/qdash/api/`      | FastAPI, Python 3.10-3.12, MongoDB, PostgreSQL  |
| Workflow Engine | `/src/qdash/workflow/` | Prefect 2.20, qubex                             |

## Directory Structure

```
qdash/
├── ui/                      # Frontend (see docs/development/ui/)
├── src/qdash/
│   ├── api/                 # Backend API (see docs/development/api/)
│   └── workflow/            # Workflow engine (see docs/development/workflow/)
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

For detailed setup instructions, see [docs/development/setup.md](docs/development/setup.md).

## Key Documentation

| Topic              | Location                                                                     |
| ------------------ | ---------------------------------------------------------------------------- |
| UI Guidelines      | [docs/development/ui/guidelines.md](docs/development/ui/guidelines.md)       |
| UI Architecture    | [docs/development/ui/architecture.md](docs/development/ui/architecture.md)   |
| API Design         | [docs/development/api/design.md](docs/development/api/design.md)             |
| Development Flow   | [docs/development/development-flow.md](docs/development/development-flow.md) |
| Database Structure | [docs/reference/database-structure.md](docs/reference/database-structure.md) |
| Docs Guidelines    | [docs/development/docs-guidelines.md](docs/development/docs-guidelines.md)   |

## Claude Code Custom Commands

| Command           | Description                                           |
| ----------------- | ----------------------------------------------------- |
| `/commit`         | Analyze changes and suggest a commit message          |
| `/suggest-commit` | Generate commit message suggestion without committing |
| `/auto-commit`    | Automatically commit with generated message           |

## Notes for AI Assistants

- **Don't edit generated code**: `ui/src/client/` and `ui/src/schemas/` are auto-generated from OpenAPI
- **Regenerate after API changes**: Run `task generate` when backend API changes
- **Follow existing patterns**: Check `docs/development/ui/guidelines.md` for coding standards
- **Follow docs guidelines**: Check `docs/development/docs-guidelines.md` when writing documentation
- **Use conventional commits**: See `docs/development/development-flow.md`

## Useful Links

- [DeepWiki](https://deepwiki.com/oqtopus-team/qdash) - AI-powered codebase exploration
- [Issue Tracker](https://github.com/oqtopus-team/qdash/issues)
- [Slack Channel](https://oqtopus.slack.com/archives/C08KM5JPUEL)
