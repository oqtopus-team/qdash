# QDash Python Package

Python backend code for QDash.

## Module Structure

| Directory | Description |
|-----------|-------------|
| `api/` | FastAPI backend API |
| `workflow/` | Prefect workflow engine |
| `repository/` | Data access layer (Repository Pattern) |
| `datamodel/` | Domain models (for business logic) |
| `dbmodel/` | Database models (MongoDB/Bunnet) |
| `common/` | Common utilities |
| `config.py` | Application settings |

## Entry Points

- **API**: `api/main.py` - FastAPI application
- **Workflow**: `workflow/deployment_service.py` - Prefect deployment

## Documentation

See [docs/development/](../../docs/development/) for details.

- [API Design Guidelines](../../docs/development/api/design.md)
- [Workflow Engine Architecture](../../docs/development/workflow/engine-architecture.md)
- [Development Setup](../../docs/development/setup.md)
