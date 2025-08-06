# Codebase Structure

## Directory Layout

```
qdash/
├── ui/                      # Frontend React application (Next.js)
│   ├── src/                 # React components and pages
│   ├── public/              # Static assets
│   ├── package.json         # Bun dependencies and scripts
│   └── Dockerfile          # Frontend container
├── src/
│   ├── qdash/
│   │   ├── api/            # FastAPI backend
│   │   │   ├── routers/    # API route handlers
│   │   │   ├── schemas/    # Pydantic schemas
│   │   │   ├── lib/        # Utility libraries
│   │   │   ├── db/         # Database session management
│   │   │   └── main.py     # FastAPI application entry
│   │   ├── workflow/       # Prefect workflow engine
│   │   │   ├── worker/     # Prefect workers and tasks
│   │   │   └── deployment/ # Workflow deployments
│   │   ├── dbmodel/        # Database models (MongoDB/PostgreSQL)
│   │   ├── datamodel/      # Data models and schemas
│   │   ├── cli/            # CLI tools
│   │   ├── slack_agent/    # Slack AI assistant
│   │   │   ├── agent.py    # Main agent logic
│   │   │   ├── tools.py    # Agent tools
│   │   │   └── main.py     # Slack app entry
│   │   └── config.py       # Configuration management
├── tests/                   # Test files
├── docs/                    # Documentation
├── scripts/                 # Utility scripts
├── config/                 # Configuration files
├── .devcontainer/          # VSCode dev container
├── compose.yaml            # Docker Compose services
├── Taskfile.yaml          # Task runner commands
└── pyproject.toml         # Python project configuration
```

## Key Components

### API Routers (src/qdash/api/routers/)
- `calibration.py` - Calibration workflow management
- `menu.py` - Menu and experiment configuration
- `settings.py` - Application settings
- `execution.py` - Workflow execution tracking
- `chip.py` - Quantum chip management
- `auth.py` - Authentication
- `parameter.py` - Parameter configuration
- `backend.py` - Backend operations

### Docker Services
- `mongo` - MongoDB database (port 27017)
- `postgres` - PostgreSQL database (port 5432)
- `prefect-server` - Prefect UI (port 4200)
- `workflow` - QDash workflow worker
- `api` - FastAPI backend (port 5715)
- `ui` - Next.js frontend (port 3000)
- `slack-agent` - Slack AI assistant

### Database Collections
- **MongoDB**: Calibration data, execution logs, device configurations, user settings
- **PostgreSQL**: Prefect workflow metadata, execution state tracking