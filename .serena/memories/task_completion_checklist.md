# Task Completion Checklist

When completing development tasks in QDash, follow this checklist to ensure code quality and consistency:

## 1. Code Formatting and Linting

### Python Code
```bash
# Format Python code
ruff format .

# Check and fix linting issues
ruff check --fix .

# Type checking
mypy src/
```

### TypeScript/Frontend Code
```bash
cd ui
# Format and lint UI code
bun run fmt
# or
task fmt-ui
```

### All Code (Recommended)
```bash
# Format both Python and TypeScript
task fmt
```

## 2. Testing
```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=src/qdash

# Run specific test file
pytest tests/qdash/api/test_main.py
```

## 3. API Client Generation
If backend API changes were made:
```bash
# Regenerate frontend API client
task generate
# or
cd ui && bun run generate-qdash
```

## 4. Build Verification
```bash
# Build frontend to check for errors
cd ui && bun run build

# For Docker changes, test builds
task build-api      # If API changed
task build-workflow # If workflow changed
```

## 5. Documentation Updates
If applicable:
```bash
# Update database schema docs
task tbls-docs

# Build documentation
task build-docs
```

## 6. Export Requirements
If dependencies changed:
```bash
# Export all requirements files
task export-all
```

## 7. Git Workflow
```bash
# Check status
git status

# Stage changes
git add .

# Commit with conventional commits format
git commit -m "feat: add new feature"
# or "fix: resolve bug" or "docs: update readme"

# Push to feature branch
git push origin feat/feature-name
```

## Pre-commit Checklist Summary
1. ✅ Code formatted (ruff format)
2. ✅ Linting passed (ruff check)  
3. ✅ Type checking passed (mypy)
4. ✅ Tests passing (pytest)
5. ✅ Frontend builds successfully
6. ✅ API client regenerated (if needed)
7. ✅ Requirements exported (if deps changed)
8. ✅ Commit follows conventional format

## Development Server Testing
Before committing, verify functionality:
```bash
# Start backend
uvicorn src.qdash.api.main:app --reload

# In another terminal, start frontend
cd ui && bun run dev

# Or use Docker Compose for full stack
docker compose up
```

## Branch Strategy
- Main branch: `develop`
- Feature branches: `feat/feature-name`
- Bug fixes: `fix/bug-description`
- Submit PRs to `develop` branch