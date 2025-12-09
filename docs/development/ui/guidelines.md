# UI Development Guidelines for QDash

This document defines the UI development conventions and standards for the QDash project. All contributors should follow these guidelines when creating new pages, components, or features.

## Table of Contents

1. [Technology Stack](#technology-stack)
2. [Project Structure](#project-structure)
3. [Naming Conventions](#naming-conventions)
4. [Component Design](#component-design)
5. [State Management](#state-management)
6. [API Integration](#api-integration)
7. [Styling Guidelines](#styling-guidelines)
8. [TypeScript Best Practices](#typescript-best-practices)
9. [Code Quality](#code-quality)
10. [Development Workflow](#development-workflow)

---

## Technology Stack

### Core Technologies

| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 14.x | React framework with App Router |
| React | 18.x | UI library |
| TypeScript | 5.x | Type-safe JavaScript |
| Bun | 1.x+ | Package manager and runtime |

### UI Libraries

| Library | Purpose |
|---------|---------|
| Tailwind CSS | Utility-first CSS framework |
| DaisyUI | Component library built on Tailwind |
| Plotly.js | Data visualization and charts |
| React Flow | Node-based diagrams and workflows |
| React Icons | Icon components |

### State Management

| Library | Purpose |
|---------|---------|
| TanStack Query (React Query) | Server state management and caching |
| React Context | Global client state (theme, user, project) |
| nuqs | URL query string state management |

---

## Project Structure

### Directory Layout

```
ui/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── (auth)/             # Protected routes (require login)
│   │   │   ├── admin/          # Admin page
│   │   │   ├── analysis/       # Analysis page
│   │   │   ├── chip/           # Chip management
│   │   │   ├── execution/      # Execution monitoring
│   │   │   ├── files/          # File management
│   │   │   ├── flow/           # Flow editor
│   │   │   ├── metrics/        # Metrics dashboard
│   │   │   ├── setting/        # Settings page
│   │   │   └── tasks/          # Task management
│   │   ├── (public)/           # Public routes (no auth required)
│   │   │   └── login/          # Login page
│   │   ├── providers/          # App-level providers
│   │   ├── globals.css         # Global styles
│   │   ├── layout.tsx          # Root layout
│   │   ├── page.tsx            # Root page (redirect)
│   │   └── providers.tsx       # Provider composition
│   ├── client/                 # Auto-generated API client (DO NOT EDIT)
│   ├── components/             # Reusable components
│   │   ├── charts/             # Chart components (Plotly wrappers)
│   │   ├── features/           # Feature-specific components
│   │   ├── layout/             # Layout components (Navbar, Sidebar)
│   │   ├── selectors/          # Selection components (dropdowns, etc.)
│   │   └── ui/                 # Generic UI components
│   ├── contexts/               # React Context providers
│   ├── hooks/                  # Custom React hooks
│   ├── lib/                    # Utilities and configurations
│   │   ├── api/                # API client configuration
│   │   ├── config/             # App configuration
│   │   └── utils/              # Utility functions
│   ├── schemas/                # Auto-generated TypeScript types (DO NOT EDIT)
│   └── types/                  # Manual type definitions
├── public/                     # Static assets
├── eslint.config.mjs           # ESLint configuration
├── orval.config.cjs            # API client generation config
├── tailwind.config.ts          # Tailwind CSS configuration
└── tsconfig.json               # TypeScript configuration
```

### Route Groups

Next.js App Router uses **route groups** (folders in parentheses) for organization:

- `(auth)/` - Routes requiring authentication. Protected by middleware.
- `(public)/` - Routes accessible without authentication.

```tsx
// Example: src/app/(auth)/metrics/page.tsx
// Accessible at: /metrics (requires login)

// Example: src/app/(public)/login/page.tsx
// Accessible at: /login (no auth required)
```

---

## Naming Conventions

### Files and Directories

| Type | Convention | Example |
|------|------------|---------|
| Page files | `page.tsx` | `src/app/(auth)/metrics/page.tsx` |
| Layout files | `layout.tsx` | `src/app/(auth)/layout.tsx` |
| Components | PascalCase | `MetricsChart.tsx` |
| Hooks | camelCase with `use` prefix | `useQubitData.ts` |
| Contexts | PascalCase with `Context` suffix | `ProjectContext.tsx` |
| Utilities | camelCase | `formatDate.ts` |
| Types | PascalCase | `ChipTypes.ts` |

### Component Naming

```tsx
// ✅ Good - PascalCase, descriptive
export function MetricsDashboard() { ... }
export function ChipSelector() { ... }
export function TaskResultsTable() { ... }

// ❌ Bad
export function metricsDashboard() { ... }  // camelCase
export function Metrics() { ... }            // Too generic
export function MD() { ... }                 // Abbreviation
```

### Hook Naming

```tsx
// ✅ Good - "use" prefix, descriptive
export function useQubitData(qid: string) { ... }
export function useTimeRange() { ... }
export function useProjectContext() { ... }

// ❌ Bad
export function qubitData() { ... }         // Missing "use" prefix
export function useData() { ... }           // Too generic
```

---

## Component Design

### Component Organization

Organize components by feature and reusability:

```
components/
├── ui/                         # Generic, reusable UI components
│   ├── Button.tsx
│   ├── Card.tsx
│   ├── DataTable.tsx
│   └── Modal.tsx
├── charts/                     # Chart components
│   ├── TaskFigure.tsx
│   └── PlotlyChart.tsx
├── features/                   # Feature-specific components
│   ├── analysis/
│   │   ├── HistogramView.tsx
│   │   └── CDFView.tsx
│   ├── chip/
│   │   ├── ChipPageContent.tsx
│   │   └── QubitGrid.tsx
│   └── metrics/
│       └── MetricsView.tsx
├── layout/                     # Layout components
│   ├── AppLayout.tsx
│   ├── Navbar.tsx
│   └── Sidebar.tsx
└── selectors/                  # Selection components
    ├── ChipSelector.tsx
    └── DateRangeSelector.tsx
```

### Component Structure

```tsx
// ✅ Good - Clear structure with types
import { useState } from "react";
import type { ChipData } from "@/schemas";

interface ChipCardProps {
  chip: ChipData;
  onSelect: (chipId: string) => void;
  isSelected?: boolean;
}

export function ChipCard({ chip, onSelect, isSelected = false }: ChipCardProps) {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <div
      className={`card ${isSelected ? "border-primary" : ""}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={() => onSelect(chip.chip_id)}
    >
      <h3>{chip.chip_id}</h3>
      {/* ... */}
    </div>
  );
}
```

### Props Interface

Always define props using TypeScript interfaces:

```tsx
// ✅ Good - Explicit interface
interface DataTableProps {
  data: Record<string, unknown>[];
  columns: ColumnDefinition[];
  onRowClick?: (row: Record<string, unknown>) => void;
  isLoading?: boolean;
}

export function DataTable({ data, columns, onRowClick, isLoading = false }: DataTableProps) {
  // ...
}

// ❌ Bad - Inline types or any
export function DataTable({ data, columns }: { data: any; columns: any }) {
  // ...
}
```

---

## State Management

### Server State with TanStack Query

Use TanStack Query for all API data fetching:

```tsx
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getChipList, updateChip } from "@/client/chip/chip";

// ✅ Good - Query with proper typing
export function ChipList() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["chips"],
    queryFn: () => getChipList(),
  });

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} />;

  return (
    <ul>
      {data?.chips.map((chip) => (
        <li key={chip.chip_id}>{chip.chip_id}</li>
      ))}
    </ul>
  );
}

// ✅ Good - Mutation with cache invalidation
export function useUpdateChip() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: { chipId: string; data: UpdateChipRequest }) =>
      updateChip(params.chipId, params.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chips"] });
    },
  });
}
```

### Query Key Conventions

```tsx
// ✅ Good - Hierarchical query keys
queryKey: ["chips"]                              // All chips
queryKey: ["chips", chipId]                      // Specific chip
queryKey: ["chips", chipId, "qubits"]            // Qubits for a chip
queryKey: ["chips", chipId, "qubits", qid]       // Specific qubit

// ✅ Good - With filters
queryKey: ["tasks", { chipId, status: "active" }]
```

### Client State with Context

Use React Context for global client state:

```tsx
// contexts/ProjectContext.tsx
import { createContext, useContext, useState, ReactNode } from "react";

interface ProjectContextType {
  selectedProject: string | null;
  setSelectedProject: (project: string) => void;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [selectedProject, setSelectedProject] = useState<string | null>(null);

  return (
    <ProjectContext.Provider value={{ selectedProject, setSelectedProject }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProjectContext() {
  const context = useContext(ProjectContext);
  if (!context) {
    throw new Error("useProjectContext must be used within a ProjectProvider");
  }
  return context;
}
```

### URL State with nuqs

Use `nuqs` for URL-synchronized state:

```tsx
import { useQueryState, parseAsString, parseAsInteger } from "nuqs";

export function FilteredList() {
  // State synced to URL: ?search=foo&page=2
  const [search, setSearch] = useQueryState("search", parseAsString.withDefault(""));
  const [page, setPage] = useQueryState("page", parseAsInteger.withDefault(1));

  return (
    <div>
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search..."
      />
      {/* ... */}
    </div>
  );
}
```

---

## API Integration

### Auto-Generated Client

API client code is auto-generated from OpenAPI spec. **Never edit files in `src/client/` or `src/schemas/`**.

```bash
# Regenerate API client
task generate
```

### Using Generated Hooks

```tsx
import { useGetChipList } from "@/client/chip/chip";
import type { ChipSummary } from "@/schemas";

export function ChipSelector() {
  const { data, isLoading } = useGetChipList();

  if (isLoading) return <LoadingSpinner />;

  return (
    <select>
      {data?.chips.map((chip: ChipSummary) => (
        <option key={chip.chip_id} value={chip.chip_id}>
          {chip.chip_id}
        </option>
      ))}
    </select>
  );
}
```

### Type Annotations for Callbacks

Always add explicit type annotations for mutation callbacks:

```tsx
import { useMutation } from "@tanstack/react-query";
import { executeFlow } from "@/client/flow/flow";
import type { ExecuteFlowResponse } from "@/schemas";
import type { AxiosResponse } from "axios";

// ✅ Good - Explicit types for callbacks
const mutation = useMutation({
  mutationFn: () => executeFlow(flowName),
  onSuccess: (response: AxiosResponse<ExecuteFlowResponse>) => {
    console.log("Execution started:", response.data.execution_id);
  },
  onError: (error: Error) => {
    console.error("Failed to execute:", error.message);
  },
});

// ❌ Bad - Implicit any types
const mutation = useMutation({
  mutationFn: () => executeFlow(flowName),
  onSuccess: (response) => {  // 'response' implicitly has 'any' type
    console.log(response.data.execution_id);
  },
});
```

### Array Method Type Annotations

Add type annotations to array callbacks to avoid implicit `any`:

```tsx
import type { TaskInfo, ChipSummary } from "@/schemas";

// ✅ Good - Explicit types
const activeChips = chips.filter((chip: ChipSummary) => chip.status === "active");
const chipNames = chips.map((chip: ChipSummary) => chip.chip_id);
const hasTask = tasks.some((task: TaskInfo) => task.name === targetName);

// ❌ Bad - Implicit any
const activeChips = chips.filter((chip) => chip.status === "active");
```

---

## Styling Guidelines

### Tailwind CSS Classes

Use Tailwind CSS utility classes for styling:

```tsx
// ✅ Good - Tailwind utilities
<div className="flex items-center gap-4 p-4 bg-base-200 rounded-lg">
  <h2 className="text-xl font-bold text-primary">Title</h2>
  <p className="text-sm text-base-content/70">Description</p>
</div>

// ❌ Bad - Inline styles
<div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
  <h2 style={{ fontSize: "1.25rem", fontWeight: "bold" }}>Title</h2>
</div>
```

### DaisyUI Components

Use DaisyUI component classes for consistent UI:

```tsx
// Buttons
<button className="btn btn-primary">Primary</button>
<button className="btn btn-secondary btn-sm">Small Secondary</button>
<button className="btn btn-outline btn-error">Outline Error</button>

// Cards
<div className="card bg-base-100 shadow-xl">
  <div className="card-body">
    <h2 className="card-title">Card Title</h2>
    <p>Card content</p>
    <div className="card-actions justify-end">
      <button className="btn btn-primary">Action</button>
    </div>
  </div>
</div>

// Form inputs
<input type="text" className="input input-bordered w-full" />
<select className="select select-bordered">
  <option>Option 1</option>
</select>

// Tables
<table className="table table-zebra">
  <thead>
    <tr><th>Name</th><th>Value</th></tr>
  </thead>
  <tbody>
    <tr><td>Row 1</td><td>Value 1</td></tr>
  </tbody>
</table>
```

### Theme Support

QDash supports light and dark themes via DaisyUI:

```tsx
// Use semantic color classes (auto-adjust to theme)
<div className="bg-base-100 text-base-content">
  <span className="text-primary">Primary color</span>
  <span className="text-secondary">Secondary color</span>
  <span className="text-accent">Accent color</span>
</div>

// Avoid hardcoded colors
// ❌ Bad
<div className="bg-white text-black">...</div>

// ✅ Good
<div className="bg-base-100 text-base-content">...</div>
```

---

## TypeScript Best Practices

### Strict Mode

The project uses TypeScript strict mode. Ensure all types are explicit:

```json
// tsconfig.json
{
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  }
}
```

### Import Types

Use `import type` for type-only imports:

```tsx
// ✅ Good - Type-only import
import type { ChipSummary, TaskInfo } from "@/schemas";
import type { AxiosResponse } from "axios";

// Regular import for values
import { useQuery } from "@tanstack/react-query";
```

### Avoid `any`

Never use `any` type. Use proper types or `unknown` with type guards:

```tsx
// ✅ Good
function processData(data: Record<string, unknown>) {
  if (typeof data.name === "string") {
    console.log(data.name);
  }
}

// ❌ Bad
function processData(data: any) {
  console.log(data.name);
}
```

### Type Assertions

Prefer type guards over type assertions:

```tsx
// ✅ Good - Type guard
function isChipData(data: unknown): data is ChipData {
  return typeof data === "object" && data !== null && "chip_id" in data;
}

if (isChipData(response)) {
  console.log(response.chip_id);
}

// ❌ Bad - Type assertion
const chip = response as ChipData;  // Unsafe
```

---

## Code Quality

### ESLint Configuration

The project uses ESLint with the following configuration:

```javascript
// eslint.config.mjs
export default [
  {
    ignores: ["node_modules/**", ".next/**", "src/schemas/**", "src/client/**"],
  },
  {
    files: ["**/*.{ts,tsx}"],
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
];
```

### Running Linters

```bash
# Run ESLint
bun run lint

# Fix auto-fixable issues
bun run fmt

# Type check
bunx tsc --noEmit
```

### Pre-commit Checks

Before committing, ensure:

1. **Type check passes**: `bunx tsc --noEmit`
2. **Lint passes**: `bun run lint`
3. **Build succeeds**: `bun run build`

---

## Development Workflow

### Local Development

```bash
# Install dependencies
bun install

# Start development server
bun run dev

# Access at http://localhost:3000
```

### API Client Generation

When backend API changes:

```bash
# From project root (requires running API server)
task generate
```

### Build for Production

```bash
# Build production bundle
bun run build

# Start production server
bun run start
```

### Common Tasks

| Command | Description |
|---------|-------------|
| `bun run dev` | Start development server |
| `bun run build` | Build for production |
| `bun run lint` | Run ESLint |
| `bun run fmt` | Fix ESLint issues |
| `bunx tsc --noEmit` | Type check |
| `task generate` | Regenerate API client |

---

## Summary

### Key Principles

1. **Use TypeScript strictly** - No implicit `any`, explicit types for all callbacks
2. **Follow naming conventions** - PascalCase for components, camelCase for hooks
3. **Organize by feature** - Group related components together
4. **Use TanStack Query** - For all server state management
5. **Use DaisyUI** - For consistent, theme-aware UI components
6. **Never edit generated code** - `src/client/` and `src/schemas/` are auto-generated

### Quick Reference

```tsx
// Component template
import type { SomeType } from "@/schemas";

interface MyComponentProps {
  data: SomeType;
  onAction: (id: string) => void;
}

export function MyComponent({ data, onAction }: MyComponentProps) {
  const { data: queryData, isLoading } = useQuery({
    queryKey: ["myData", data.id],
    queryFn: () => fetchData(data.id),
  });

  if (isLoading) return <div className="loading loading-spinner" />;

  return (
    <div className="card bg-base-100">
      <div className="card-body">
        <h2 className="card-title">{data.name}</h2>
        <button className="btn btn-primary" onClick={() => onAction(data.id)}>
          Action
        </button>
      </div>
    </div>
  );
}
```
