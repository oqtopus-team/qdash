# Code Style and Conventions

## General Conventions
- **EditorConfig**: Universal settings in `.editorconfig`
  - Indent style: spaces (2 for most files, 4 for Python)
  - End of line: LF
  - Charset: UTF-8
  - Trim trailing whitespace: true
  - Insert final newline: true

## Python Code Style

### Formatting and Linting
- **Formatter**: Ruff format (configured in pyproject.toml)
- **Linter**: Ruff check with extensive rule set
- **Type Checker**: mypy with strict settings
- **Line Length**: 100 characters

### Ruff Configuration (pyproject.toml)
- **Selected Rules**: "ALL" (comprehensive rule set)
- **Key Ignored Rules**:
  - COM812, ISC001 - Formatting conflicts
  - D100, D104, D107, D203, D213 - Docstring rules
  - CPY001 - Copyright notice
  - ERA001 - Commented code
  - Various others for pragmatic development

### Python Conventions
- **Type Hints**: Required (mypy disallow_untyped_defs = true)
- **Docstrings**: Not required for all functions (D102 ignored)
- **Import Style**: Organized and explicit
- **Naming**: Follow PEP 8 conventions
- **Indentation**: 4 spaces (as per .editorconfig)

### Test File Exceptions
Tests have relaxed rules including:
- No type annotations required (ANN201, ANN205, ANN401)
- No docstrings required (D)
- Magic numbers allowed (PLR2004)
- Assert statements allowed (S101)

## TypeScript/JavaScript Code Style

### Frontend (UI) Conventions
- **Formatter**: Prettier
- **Linter**: ESLint with TypeScript support
- **Package Manager**: Bun
- **Indentation**: 2 spaces
- **Framework**: Next.js 14 with TypeScript

### ESLint Configuration
- TypeScript parser and plugin
- React hooks plugin
- Import plugin for module organization
- Max warnings: 0 (strict enforcement)

## API Design
- **OpenAPI**: Auto-generated documentation
- **Schema Generation**: Automated with orval for frontend
- **Authentication**: X-Username header (development mode)
- **Route Naming**: Custom unique ID generation