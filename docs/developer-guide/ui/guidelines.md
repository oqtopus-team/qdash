# UI Development Guidelines

Conventions for code under `ui/`: the stack, where files live, how they are named, and how to lint, build, and regenerate the client. Component and state patterns are in [components.md](./components.md), styling in [styling.md](./styling.md), type rules in [typescript.md](./typescript.md), and API client usage in [api-integration.md](./api-integration.md).

## Technology Stack

### Core Technologies

| Technology | Version | Purpose                         |
| ---------- | ------- | ------------------------------- |
| Next.js    | 16.x    | React framework with App Router |
| React      | 19.x    | UI library                      |
| TypeScript | 6.x     | Type-safe JavaScript            |
| Bun        | 1.4.0+  | Package manager and runtime     |

### UI Libraries

| Library              | Purpose                                |
| -------------------- | -------------------------------------- |
| Tailwind CSS         | Utility-first CSS framework            |
| DaisyUI              | Visual components, themes, and semantic colors |
| Radix UI             | Headless primitives for complex interaction behavior |
| plotly.js-dist-min   | Plotly chart rendering                 |
| XYFlow               | Node-based diagrams and workflows      |
| Lucide React         | Icon components (see [design-policy.md](./design-policy.md)) |

How DaisyUI and Radix divide responsibilities: [components.md](./components.md#daisyui-and-radix-responsibilities). How to apply Tailwind and DaisyUI classes: [styling.md](./styling.md).

### State Management

| Library                      | Purpose                                    |
| ---------------------------- | ------------------------------------------ |
| TanStack Query (React Query) | Server state management and caching        |
| React Context                | Global client state (theme, user, project) |
| nuqs                         | URL query string state management          |

Usage patterns for each: [components.md](./components.md#state-management).

---

## Project Structure

### Directory Layout

```
ui/
├── src/
│   ├── app/                    # Next.js App Router (pages and routes ONLY)
│   │   ├── (auth)/             # Protected routes (require login)
│   │   │   ├── admin/          # Admin page
│   │   │   ├── analysis/       # Analysis page
│   │   │   ├── chat/           # Copilot chat
│   │   │   ├── chip/           # Chip management
│   │   │   ├── execution/      # Execution monitoring
│   │   │   ├── files/          # File management
│   │   │   ├── home/           # Home (default landing page)
│   │   │   ├── inbox/          # Notification inbox
│   │   │   ├── metrics/        # Metrics dashboard
│   │   │   ├── provenance/     # Data provenance
│   │   │   ├── settings/       # Settings page
│   │   │   ├── task-results/   # Task result viewer
│   │   │   ├── tasks/          # Task management
│   │   │   └── workflow/       # Workflow editor
│   │   ├── (public)/           # Public routes (no auth required)
│   │   │   └── login/          # Login page
│   │   ├── api/                # API route handlers (SSE streaming)
│   │   ├── globals.css         # Global styles
│   │   ├── layout.tsx          # Root layout
│   │   ├── page.tsx            # Root page (redirects to /home)
│   │   └── providers.tsx       # Provider composition
│   ├── client/                 # Auto-generated API client (DO NOT EDIT)
│   ├── components/             # Reusable components
│   │   ├── charts/             # Chart components (Plotly wrappers)
│   │   ├── features/           # Feature-specific components
│   │   │   ├── admin/          # Admin page content
│   │   │   ├── files/          # Files page content
│   │   │   ├── tasks/          # Tasks page content
│   │   │   └── ...             # Other feature directories
│   │   ├── layout/             # Layout components (AppLayout, ChatSidebar)
│   │   ├── selectors/          # Selection components (dropdowns, etc.)
│   │   └── ui/                 # Generic UI components
│   ├── contexts/               # ALL React Context/Provider files
│   │   ├── AxiosContext.tsx     # Axios interceptor provider
│   │   ├── ThemeContext.tsx     # Theme provider
│   │   ├── AuthContext.tsx      # Authentication context
│   │   ├── ProjectContext.tsx   # Project selection context
│   │   ├── SidebarContext.tsx   # Sidebar state context
│   │   └── ChatDockContext.tsx  # Chat sidebar / floating window state
│   ├── hooks/                  # Custom React hooks
│   │   ├── __tests__/          # Hook unit tests
│   │   ├── url-state/          # URL state hooks (split from useUrlState)
│   │   │   ├── __tests__/      # URL state hook tests
│   │   │   ├── types.ts        # Shared types (TimeRange, SelectionMode, etc.)
│   │   │   ├── useChipUrlState.ts
│   │   │   ├── useExecutionUrlState.ts
│   │   │   ├── useAnalysisUrlState.ts
│   │   │   ├── use*UrlState.ts # Other URL state hooks
│   │   │   └── index.ts        # Barrel re-export
│   │   └── use*.ts             # Other hooks (flat)
│   ├── lib/                    # Utilities and configurations
│   │   ├── api/                # API client configuration
│   │   └── utils/              # Utility functions
│   │       ├── datetime.ts     # Date/time formatting
│   │       ├── grid-layout.ts  # Grid layout calculations
│   │       ├── grid-position.ts # Grid position calculations
│   │       └── qid.ts          # Qubit ID utilities
│   ├── schemas/                # Auto-generated TypeScript types (DO NOT EDIT)
│   └── types/                  # Manual type definitions
├── public/                     # Static assets
├── vitest.config.mts           # Vitest test configuration
├── vitest.setup.ts             # Test setup (jest-dom matchers)
├── .oxlintrc.json              # Oxlint configuration
├── .oxfmt.json                 # Oxfmt configuration
├── orval.config.cjs            # API client generation config
└── tsconfig.json               # TypeScript configuration
```

How components are organized inside `components/`: [components.md](./components.md#component-organization).

### Route Groups

Next.js App Router uses **route groups** (folders in parentheses) for organization:

- `(auth)/` - Routes requiring authentication. Protected by Next.js proxy.
- `(public)/` - Routes accessible without authentication.

File-to-URL examples and the layout hierarchy: [architecture.md](./architecture.md#route-groups).

### Key Conventions

#### Import Paths

| Module                | Import from              | NOT from                  |
| --------------------- | ------------------------ | ------------------------- |
| Utilities             | `@/lib/utils/*`          | ~~`@/utils/*`~~ (removed) |
| Providers & Contexts  | `@/contexts/*`           | ~~`@/app/providers/*`~~ (removed) |
| URL State hooks       | `@/hooks/useUrlState` or `@/hooks/url-state` | Direct file paths |

#### Export Rules

| File type               | Export style      | Example                                          |
| ----------------------- | ----------------- | ------------------------------------------------ |
| `page.tsx`, `layout.tsx`| `default export`  | `export default function AdminPage() {}`         |
| All other files         | `named export`    | `export function AdminPageContent() {}`          |
| Exceptions for `dynamic()` | both           | Named + default for components loaded via `next/dynamic` |

#### Page Pattern

All `page.tsx` files should be thin wrappers that delegate to a `*PageContent` component:

```tsx
// app/(auth)/admin/page.tsx - Thin wrapper
"use client";
import { AdminPageContent } from "@/components/features/admin/AdminPageContent";

export default function AdminPage() {
  return <AdminPageContent />;
}
```

Do NOT put business logic, state management, or large JSX in `page.tsx` files.

---

## Naming Conventions

### Files and Directories

| Type         | Convention                       | Example                           |
| ------------ | -------------------------------- | --------------------------------- |
| Page files   | `page.tsx`                       | `src/app/(auth)/metrics/page.tsx` |
| Layout files | `layout.tsx`                     | `src/app/(auth)/layout.tsx`       |
| Components   | PascalCase                       | `MetricsChart.tsx`                |
| Hooks        | camelCase with `use` prefix      | `useQubitData.ts`                 |
| Contexts     | PascalCase with `Context` suffix | `ProjectContext.tsx`              |
| Utilities    | camelCase                        | `formatDate.ts`                   |
| Types        | PascalCase                       | `ChipTypes.ts`                    |

### Component Naming

```tsx
// Good - PascalCase, descriptive
export function MetricsDashboard() { ... }
export function ChipSelector() { ... }
export function TaskResultsTable() { ... }

// Bad
export function metricsDashboard() { ... }  // camelCase
export function Metrics() { ... }            // Too generic
export function MD() { ... }                 // Abbreviation
```

### Hook Naming

```tsx
// Good - "use" prefix, descriptive
export function useQubitData(qid: string) { ... }
export function useTimeRange() { ... }
export function useProjectContext() { ... }

// Bad
export function qubitData() { ... }         // Missing "use" prefix
export function useData() { ... }           // Too generic
```

---

## Code Quality

### Oxlint Configuration

The project uses `oxlint` with the `typescript`, `react`, and `nextjs` plugins. The rule set lives in `ui/.oxlintrc.json` and is reproduced in [testing.md](./testing.md#oxlint-configuration).

**Note:** `no-explicit-any` is set to `warn` to encourage proper typing. Prefix unused variables with `_` to suppress `no-unused-vars` warnings. The type rules themselves are in [typescript.md](./typescript.md).

### Running Linters

```bash
# Run oxlint
bun run lint

# Auto-format
bun run fmt

# Type check
bunx tsc --noEmit

# Check formatting without rewriting files
bun run fmt:check
```

### Pre-commit Checks

Before committing, ensure:

1. **Tests pass**: `bun run test:run`
2. **Type check passes**: `bunx tsc --noEmit`
3. **Lint passes**: `bun run lint`
4. **Build succeeds**: `bun run build`

---

## Development Workflow

### Local Development

```bash
# Install dependencies
task dev-local-setup

# Start the host-side development stack
task dev-local

# Access at http://localhost:5714
```

### API Client Generation

When backend API changes:

```bash
# From project root (requires running API server)
task generate
```

Never edit the generated `src/client/` and `src/schemas/` directories; how to use the generated hooks is in [api-integration.md](./api-integration.md).

### Build for Production

```bash
# Build production bundle
bun run build
```

### Common Tasks

| Command             | Description                          |
| ------------------- | ------------------------------------ |
| `bun run dev`       | Start development server             |
| `bun run build`     | Build for production                 |
| `bun run test`      | Run tests in watch mode              |
| `bun run test:run`  | Run tests once (CI-friendly)         |
| `task test-ui`      | Run UI tests from project root       |
| `bun run lint`      | Run oxlint                           |
| `bun run lint:fix`  | Apply oxlint auto-fixes              |
| `bun run fmt`       | Format files with oxfmt              |
| `bun run fmt:check` | Check formatting with oxfmt          |
| `bunx tsc --noEmit` | Type check                           |
| `task generate`     | Regenerate API client                |

## References

This guide is based on the following official documentation:

| Topic | Reference |
| --- | --- |
| Project Structure | [Next.js Project Structure](https://nextjs.org/docs/getting-started/project-structure) |
| App Router | [Next.js App Router](https://nextjs.org/docs/app) |
| Data Fetching | [Next.js Data Fetching Patterns](https://nextjs.org/docs/app/building-your-application/data-fetching/patterns) |
| Server/Client Components | [Next.js Server and Client Composition Patterns](https://nextjs.org/docs/app/building-your-application/rendering/composition-patterns) |
| TanStack Query | [TanStack Query Documentation](https://tanstack.com/query/latest/docs/framework/react/overview) |
| nuqs (URL State) | [nuqs Documentation](https://nuqs.47ng.com/) |
| Tailwind CSS | [Tailwind CSS Documentation](https://tailwindcss.com/docs) |
| DaisyUI | [DaisyUI Components](https://daisyui.com/components/) |
| Oxc Linter | [Oxlint Documentation](https://oxc.rs/docs/guide/usage/linter.html) |
| React Hooks Rules | [React Rules of Hooks](https://react.dev/reference/rules/rules-of-hooks) |
| Plotly.js | [Plotly.js Documentation](https://plotly.com/javascript/) |
| Export Patterns | [Next.js Lazy Loading with dynamic()](https://nextjs.org/docs/app/building-your-application/optimizing/lazy-loading) |
