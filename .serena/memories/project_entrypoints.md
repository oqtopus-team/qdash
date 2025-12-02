# Project Entrypoints and Run Commands

## Main Application Entrypoints

### 1. FastAPI Backend

**Location**: `src/qdash/api/main.py`
**Purpose**: Main API server application

**Run Commands**:

```bash
# Development (hot reload)
uvicorn src.qdash.api.main:app --reload

# Production (via Docker Compose)
docker compose up api

# Manual production
gunicorn src.qdash.api.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind :5715
```

### 2. Next.js Frontend

**Location**: `ui/` directory
**Purpose**: React-based user interface

**Run Commands**:

```bash
cd ui
# Development server
bun run dev

# Production build and start
bun run build && bun run start

# Via Docker Compose
docker compose up ui
```

### 3. Prefect Workflow Engine

**Location**: `src/qdash/workflow/`
**Purpose**: Quantum calibration workflow orchestration

**Run Commands**:

```bash
# Prefect server
prefect server start --host 0.0.0.0

# Workflow worker (via Docker Compose)
docker compose up workflow
```

## CLI Tools

### 1. QDash CLI

**Location**: `src/qdash/cli/main.py`
**Purpose**: Command-line interface for QDash operations

**Usage**:

```bash
# Available after installation
qdash --help

# Direct execution
python src/qdash/cli/main.py
```

### 2. Utility Scripts

**Location**: `src/tools/`
**Available Tools**:

- `device_topology_generator.py` - Generate device topologies
- `converter.py` - Data format conversion
- `diagnose.py` - System diagnostics
- `greedy.py` - Greedy algorithm utilities

**Run Example**:

```bash
python src/tools/device_topology_generator.py
```

## Docker Compose Services

### Full Stack Development

```bash
# Start all services
docker compose up

# Start specific services
docker compose up mongo api ui

# Development profile
docker compose -f compose.dev.yaml up
```

### Individual Services

- **mongo**: MongoDB database (port 27017)
- **postgres**: PostgreSQL database (port 5432)
- **prefect-server**: Prefect UI (port 4200)
- **api**: FastAPI backend (port 5715)
- **ui**: Next.js frontend (port 3000)
- **workflow**: Prefect workflow worker

### Service Dependencies

1. **mongo** - Independent
2. **postgres** - Independent
3. **prefect-server** - Depends on postgres
4. **workflow** - Depends on mongo, prefect-server
5. **api** - Depends on mongo, prefect-server
6. **ui** - Depends on api

## Development Servers

### Hot Reload Development

```bash
# Terminal 1: Backend
uvicorn src.qdash.api.main:app --reload --port 5715

# Terminal 2: Frontend
cd ui && bun run dev

# Terminal 3: Database
docker compose up mongo postgres
```

### Port Configuration

- API: `${API_PORT:-5715}`
- Frontend: `3000`
- MongoDB: `${MONGO_PORT:-27017}`
- PostgreSQL: `${POSTGRES_PORT:-5432}`
- Prefect: `${PREFECT_PORT:-4200}`

## Environment Variables

Key variables in `.env` file:

- `API_PORT` - FastAPI server port
- `MONGO_PORT` - MongoDB port
- `POSTGRES_PORT` - PostgreSQL port
- `PREFECT_PORT` - Prefect UI port
- `NEXT_PUBLIC_API_URL` - Frontend API URL
