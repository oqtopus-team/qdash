# Development Environment Setup

## Prerequisites

Before starting development, you need to install the following tools:

### Required Tools

| Tool                                                       | Version | Description                              |
| ---------------------------------------------------------- | ------- | ---------------------------------------- |
| [Docker](https://docs.docker.com/get-docker/)              | -       | Container virtualization platform        |
| [Docker Compose](https://docs.docker.com/compose/install/) | v2+     | Management of multiple Docker containers |
| [go-task](https://taskfile.dev/installation/)              | v3.41+  | Task runner for development commands     |
| [uv](https://docs.astral.sh/uv/)                           | -       | Python package manager                   |

### Optional Tools (for local development)

| Tool                                        | Version   | Description                          |
| ------------------------------------------- | --------- | ------------------------------------ |
| [Python](https://www.python.org/downloads/) | 3.10-3.12 | Backend development                  |
| [Bun](https://bun.sh/)                      | 1.0+      | Frontend package manager and runtime |
| [Node.js](https://nodejs.org/)              | 20+       | Alternative frontend runtime         |

## Getting Started

### Clone the Repository

```shell
git clone https://github.com/oqtopus-team/qdash.git
cd qdash
```

### Initial Setup

Run the initialization script to create necessary directories and environment files:

```shell
chmod +x scripts/init.sh
scripts/init.sh
```

This script will:

- Create required data directories
- Generate `.env` file from template

### Using DevContainer (Recommended)

The recommended way to develop is using the DevContainer:

```shell
docker compose -f compose.devcontainer.yaml up -d
```

Then attach to the container using VS Code's DevContainer extension or:

```shell
docker compose -f compose.devcontainer.yaml exec devcontainer bash
```

### Install Dependencies

Inside the devcontainer:

```shell
# Install Python dependencies
pip install -e .

# Install frontend dependencies
cd ui && bun install
```

## Running Services

### Start All Services

```shell
docker compose up -d

# Or using task
task deploy-dev
```

This starts the following services:

- **mongo**: MongoDB database (port 27017)
- **mongo-express**: MongoDB admin UI (port 8081)
- **postgres**: PostgreSQL database (port 5432)
- **prefect-server**: Prefect workflow server (port 4200)
- **workflow**: Calibration workflow worker
- **deployment-service**: Prefect deployment management
- **user-flow-worker**: User flow execution worker
- **api**: FastAPI backend (port 5715)
- **ui**: Next.js frontend (port 5714)

### Access Points

| Service           | URL                        |
| ----------------- | -------------------------- |
| QDash UI          | http://localhost:5714      |
| API Documentation | http://localhost:5715/docs |
| Prefect Dashboard | http://localhost:4200      |
| MongoDB Admin     | http://localhost:8081      |

## Development Commands

### Using go-task

```shell
# Show all available tasks
task

# Deploy in dev mode
task deploy-dev

# Deploy with Cloudflare Tunnel
task deploy-prod

# Restart API service
task restart-api
```

### Code Quality

```shell
# Format all code
task fmt

# Format Python only
task fmt-python

# Format UI only
task fmt-ui

# Run linting
task lint

# Run mypy type checking
task lint-mypy
```

### Testing

```shell
# Run all tests
task test

# Run API tests only
task test-api

# Run workflow tests only
task test-workflow

# Run database model tests
task test-dbmodel

# Run tests with coverage
task test-coverage

# Run tests, stop on first failure
task test-fast
```

### Build & Generate

```shell
# Generate TypeScript API client
task generate

# Build UI
task build

# Build API Docker image
task build-api

# Build workflow Docker image
task build-workflow

# Export all requirements
task export-all
```

### Documentation

```shell
# Start docs dev server
task docs

# Build docs
task build-docs

# Generate DB schema docs
task tbls-docs
```

## Environment Variables

Key environment variables are configured in `.env`. See `.env.example` for available options:

| Variable                  | Default | Description                 |
| ------------------------- | ------- | --------------------------- |
| `API_PORT`                | 5715    | Backend API port            |
| `UI_PORT`                 | 5714    | Frontend UI port            |
| `MONGO_PORT`              | 27017   | MongoDB port                |
| `POSTGRES_PORT`           | 5432    | PostgreSQL port             |
| `PREFECT_PORT`            | 4200    | Prefect dashboard port      |
| `NEXT_PUBLIC_API_URL`     | -       | Public API URL for frontend |
| `NEXT_PUBLIC_PREFECT_URL` | -       | Prefect dashboard URL       |
