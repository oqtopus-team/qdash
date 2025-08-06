# Suggested Commands for QDash Development

## Task Runner Commands (Preferred)
Use `task` command to run predefined tasks from Taskfile.yaml:

```bash
# Show all available tasks
task

# Format all code (Python and TypeScript)
task fmt

# Generate API client from OpenAPI spec
task generate

# Format UI code only
task fmt-ui

# Export requirements files
task export-all
task export-api
task export-workflow
task export-agent

# Build Docker images
task build-api
task build-workflow

# Documentation
task docs           # Run docs dev server
task build-docs     # Build documentation
task tbls-docs      # Generate DB schema docs
```

## Python Development Commands

### Code Quality
```bash
# Format Python code
ruff format .

# Lint Python code  
ruff check .

# Fix auto-fixable issues
ruff check --fix .

# Type checking
mypy src/

# Run tests
pytest

# Run tests with coverage
pytest --cov=src/qdash
```

### Development Server
```bash
# Run API server (from project root)
uvicorn src.qdash.api.main:app --reload

# Alternative with custom port
uvicorn src.qdash.api.main:app --reload --port 5715
```

## Frontend (UI) Development Commands

### Package Management
```bash
cd ui
bun install          # Install dependencies
```

### Development
```bash
cd ui
bun run dev          # Development server
bun run build        # Production build
bun run start        # Start production server
bun run lint         # ESLint
bun run fmt          # Format with ESLint --fix
```

### API Client Generation
```bash
cd ui
bun run generate-qdash   # Generate API client from OpenAPI spec
```

## Docker Commands

### Full Stack Development
```bash
# Start all services
docker compose up

# Start in detached mode
docker compose up -d

# Build and start
docker compose up --build

# Stop services
docker compose down

# View logs
docker compose logs -f [service_name]
```

### Development Mode
```bash
# Start development services
docker compose -f compose.dev.yaml up
```

## Utility Commands

### System Commands (Linux)
- `ls` - List files
- `cd` - Change directory  
- `grep` - Search text patterns
- `find` - Find files
- `git` - Version control

### Project Specific
```bash
# Show git status
git status

# Check current branch
git branch

# View commit history
git log --oneline
```

## Environment Setup
```bash
# Copy environment template
cp .env.example .env

# Edit environment variables
nano .env
```

## Testing
```bash
# Run specific test file
pytest tests/qdash/api/test_main.py

# Run with specific markers
pytest -m "not slow"

# Verbose output
pytest -v
```