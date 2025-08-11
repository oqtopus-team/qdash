# QDash Project Reference Guide

## Project Overview

QDash is a comprehensive web platform for managing and monitoring qubit calibration workflows. It provides a user-friendly interface to manage calibration processes, track observational data, and configure calibration parameters seamlessly.

**Repository**: https://github.com/oqtopus-team/qdash
**License**: Apache 2.0
**Status**: Under active development

## Architecture

QDash follows a microservices architecture with three major components:

### 1. Frontend (UI)

- **Location**: `/ui/`
- **Technology**: React, Next.js 14, TypeScript
- **Styling**: Tailwind CSS, DaisyUI
- **State Management**: TanStack Query
- **Charts/Visualization**: Plotly.js, Nivo, React Flow
- **Code Generation**: OpenAPI TypeScript (orval)

### 2. Backend (API)

- **Location**: `/src/qdash/api/`
- **Technology**: FastAPI, Python 3.10-3.12
- **Database**: MongoDB (via Bunnet ODM), PostgreSQL
- **Authentication**: JWT with python-jose
- **API Documentation**: Auto-generated OpenAPI/Swagger

### 3. Workflow Engine

- **Location**: `/src/qdash/workflow/`
- **Technology**: Prefect 2.20
- **Purpose**: Manages qubit calibration workflows
- **Integration**: Uses qubex library for quantum experiments

### 4. Slack Agent (New Feature)

- **Location**: `/src/qdash/slack_agent/`
- **Technology**: Slack Bolt, OpenAI API
- **Purpose**: AI-powered Slack assistant for QDash operations
- **Available Tools**:
  - `get_current_time`: Get current date/time
  - `calculate`: Perform mathematical calculations
  - `get_string_length`: Measure text length
  - `web_search`: Execute web search (demo mode)
  - `get_current_chip`: Get current chip ID
  - `investigate_calibration`: Investigate calibration results and execution history
  - `get_chip_parameters`: Get chip parameter information including fidelity statistics

## Directory Structure

```
qdash/
├── ui/                      # Frontend React application
│   ├── src/
│   │   ├── app/            # Next.js app directory
│   │   │   ├── analysis/   # Analysis page components
│   │   │   ├── chip/       # Chip and qubit detail pages
│   │   │   └── ...         # Other feature pages
│   │   ├── shared/         # 🆕 Shared UI architecture (DRY compliance)
│   │   │   ├── hooks/      # Reusable custom hooks
│   │   │   ├── components/ # Reusable UI components
│   │   │   └── types/      # Shared type definitions
│   │   └── client/         # API client code
├── src/
│   ├── qdash/
│   │   ├── api/            # FastAPI backend
│   │   ├── workflow/       # Prefect workflow engine
│   │   ├── dbmodel/        # Database models
│   │   ├── datamodel/      # Data models
│   │   ├── cli/            # CLI tools
│   │   └── slack_agent/    # Slack AI assistant
├── docs/                    # Documentation
├── tests/                   # Test files
├── calib_data/             # Calibration data storage
├── config/                 # Configuration files
└── scripts/                # Utility scripts
```

## Key Technologies

### Frontend Stack

- **Framework**: Next.js 14.2.24
- **Language**: TypeScript 5.6.3
- **Package Manager**: Bun
- **Build Tool**: Next.js built-in
- **UI Components**: DaisyUI 5.0.0
- **Data Visualization**: Plotly.js, React Flow, Nivo

### Backend Stack

- **Framework**: FastAPI 0.111.1
- **Language**: Python 3.10-3.12
- **ORM/ODM**: Bunnet (MongoDB), SQLAlchemy (PostgreSQL)
- **Workflow Engine**: Prefect 2.20
- **Quantum Library**: qubex v1.4.1b1

### Infrastructure

- **Containerization**: Docker & Docker Compose
- **Databases**: MongoDB, PostgreSQL 14
- **Task Runner**: go-task v3.41.0
- **API Gateway**: Uvicorn with Gunicorn

## Development Commands

### Frontend Commands (in `/ui/` directory)

```bash
# Development server
bun run dev

# Build production
bun run build

# Start production server
bun run start

# Linting
bun run lint

# Format code
bun run fmt

# Generate API client from OpenAPI
bun run generate-qdash
```

### Backend Commands

```bash
# Run API server (from project root)
uvicorn src.qdash.api.main:app --reload

# Format Python code
ruff format .

# Lint Python code
ruff check .

# Run tests
pytest

# Type checking
mypy src/
```

### Task Commands (using go-task)

```bash
# Show all available tasks
task

# Generate API client
task generate

# Format all code
task fmt

# Build Docker images
task build-api
task build-workflow

# Export requirements
task export-all
```

## API Endpoints

The API is organized into the following router modules:

- `/api/calibration` - Calibration workflow management
- `/api/menu` - Menu and experiment configuration
- `/api/settings` - Application settings
- `/api/execution` - Workflow execution tracking
- `/api/chip` - Quantum chip management
- `/api/file` - File operations
- `/api/auth` - Authentication
- `/api/task` - Task management
- `/api/parameter` - Parameter configuration
- `/api/tag` - Tagging system
- `/api/device_topology` - Device topology management
- `/api/backend` - Backend operations

## Database Schema

### MongoDB Collections

- Calibration data
- Execution logs
- Device configurations
- User settings

### PostgreSQL Tables

- Prefect workflow metadata
- Execution state tracking
- User authentication

## Workflow System

The workflow system uses Prefect to orchestrate quantum calibration experiments:

1. User requests calibration through the UI
2. API creates a workflow request
3. Prefect workflow engine processes the request
4. qubex library performs quantum measurements
5. Results are stored in MongoDB
6. UI displays real-time progress and results

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/qdash

# Run specific test file
pytest tests/qdash/api/test_main.py
```

## Environment Variables

Key environment variables (see `.env.example`):

- `API_PORT` - API server port (default: 5715)
- `MONGO_PORT` - MongoDB port (default: 27017)
- `POSTGRES_PORT` - PostgreSQL port (default: 5432)
- `PREFECT_PORT` - Prefect UI port (default: 4200)
- `NEXT_PUBLIC_API_URL` - Frontend API URL

## Docker Compose Services

- `mongo` - MongoDB database
- `mongo-express` - MongoDB admin interface
- `postgres` - PostgreSQL database
- `prefect-server` - Prefect workflow server
- `workflow` - QDash workflow worker
- `api` - FastAPI backend
- `ui` - Next.js frontend
- `slack-agent` - Slack AI assistant

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/feature-name`)
3. Commit changes following conventional commits
4. Run tests and linting
5. Submit a pull request to the `develop` branch

## Claude Code Custom Commands

The project includes custom slash commands for Claude Code:

### Commit Commands

- `/commit` - Analyze changes and suggest a commit message
- `/suggest-commit` - Generate commit message suggestion without committing
- `/auto-commit` - Automatically commit with generated message

### Usage Examples

```
/commit
# Analyzes changes and provides a commit message with the git command

/suggest-commit
# Only suggests a message without committing

/auto-commit
# Analyzes and commits automatically
```

### Manual Scripts

If you prefer running scripts manually:

- `task commit` or `task ac` - Interactive auto-commit script
- `python scripts/git-auto-commit.py` - Python version
- `./scripts/auto-commit.sh` - Shell version (requires ANTHROPIC_API_KEY)

## Useful Links

- [Documentation](https://qdash.readthedocs.io/)
- [Slack Channel](https://oqtopus.slack.com/archives/C08KM5JPUEL)
- [Issue Tracker](https://github.com/oqtopus-team/qdash/issues)
- [DeepWiki](https://deepwiki.com/oqtopus-team/qdash)

## Notes for AI Assistants

- The project uses a microservices architecture with clear separation of concerns
- Frontend code is generated from OpenAPI specs - always regenerate after API changes
- Workflow system has exclusive locking to prevent concurrent calibrations
- The project follows Python and TypeScript best practices
- All Docker services are configured to work within a custom network
- Authentication uses a simple X-Username header (development mode)
- The Slack agent feature is newly implemented on the feat/slack-agent branch

## Problem-Solving Process

When encountering complex technical issues, especially those involving Python packaging, Git subdirectories, or build systems:

1. **Use Advanced AI Consultation**: For complex problems that seem unsolvable, use `mcp__gpt__advanced_search` with detailed context
   - Provide specific error messages and technical details
   - Include relevant file structures and configurations
   - Ask for root cause analysis and systematic solutions

2. **Example Success Case - qdash_client GitHub Installation Issue**:
   - **Problem**: `uv add "git+https://github.com/oqtopus-team/qdash.git#subdirectory=qdash_client"` appeared successful but installed no actual Python files
   - **Investigation**: Used advanced AI to analyze package discovery patterns, wheel contents, and subdirectory installation mechanics
   - **Root Cause**: Package structure was incorrect for subdirectory Git installations - needed src layout
   - **Solution**: Restructured to `qdash_client/src/qdash_client/` and updated `pyproject.toml` package discovery
   - **Verification**: Built wheel locally, tested GitHub installation, confirmed all imports work

3. **Key Techniques**:
   - Build wheels locally and inspect contents (`unzip -l dist/*.whl`) to verify actual file inclusion
   - Test installations in clean environments to avoid local conflicts
   - Use RECORD files in site-packages to understand what was actually installed
   - Check for namespace conflicts between local development files and installed packages

This systematic approach combining AI consultation with methodical debugging resolved a complex packaging issue that would have been difficult to solve through trial and error alone.

## Shared UI Architecture (`/ui/src/shared/`)

The project implements a DRY (Don't Repeat Yourself) compliant shared architecture to eliminate code duplication between analysis and qubit detail pages. This modular approach reduces maintenance overhead and ensures consistent UI/UX across the application.

### Architecture Overview

The shared directory contains reusable hooks, components, and types that are consumed by multiple pages:

```
/ui/src/shared/
├── hooks/                   # Reusable custom hooks
│   ├── useTimeRange.ts      # JST time management and auto-refresh
│   ├── useTimeseriesData.ts # Generic time series data processing
│   ├── useCorrelationData.ts # Parameter correlation analysis
│   └── useCSVExport.ts      # CSV export functionality
├── components/              # Reusable UI components
│   ├── PlotCard.tsx         # Standardized Plotly visualization container
│   ├── StatisticsCards.tsx  # Statistical analysis display
│   ├── DataTable.tsx        # Generic data table with sorting/filtering
│   └── ErrorCard.tsx        # Consistent error state display
└── types/
    └── analysis.ts          # Shared TypeScript type definitions
```

### Key Benefits

- **42% code reduction**: Eliminated 1,330+ lines of duplicate code across analysis and qubit pages
- **Consistent UX**: Unified behavior for plots, tables, errors, and time controls
- **Single source of truth**: Bug fixes and features apply automatically to all consumers
- **Type safety**: Shared TypeScript definitions prevent interface mismatches
- **Maintainability**: Centralized components enable faster development cycles

### Usage Examples

```typescript
// Using shared hooks
import { useTimeRange } from "@/shared/hooks/useTimeRange";
import { useCSVExport } from "@/shared/hooks/useCSVExport";

// Using shared components
import { PlotCard } from "@/shared/components/PlotCard";
import { DataTable } from "@/shared/components/DataTable";
import { ErrorCard } from "@/shared/components/ErrorCard";

// Using shared types
import { TimeSeriesDataPoint, ParameterKey } from "@/shared/types/analysis";
```

### Component Features

- **PlotCard**: Standardized Plotly container with loading states, error handling, and export controls
- **DataTable**: Generic table with sorting, filtering, pagination, and CSV export
- **StatisticsCards**: Statistical summaries with correlation strength indicators
- **ErrorCard**: Consistent error display with retry functionality

### Hook Capabilities

- **useTimeRange**: JST timezone handling, auto-refresh, time locking controls
- **useCSVExport**: Multi-format CSV generation with proper escaping
- **useCorrelationData**: Statistical analysis including correlation coefficients
- **useTimeseriesData**: Generic time series processing for both single and multi-qubit data

## Python Client Generation

The project generates a Python client from the OpenAPI specification:

### Client Usage

```bash
# Generate client
task generate-python-client

# Install from GitHub
pip install "git+https://github.com/oqtopus-team/qdash.git#subdirectory=qdash_client"

# Basic usage
from qdash_client import Client
from qdash_client.api.menu import list_menu

client = Client(
    base_url="http://localhost:5715",
    headers={"X-Username": "your-username"}
)
response = list_menu.sync_detailed(client=client)
if response.status_code == 200:
    menus = response.parsed
```
