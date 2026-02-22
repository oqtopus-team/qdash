# UI Architecture

## Architecture Overview

![UI Architecture](../../diagrams/ui-architecture.drawio.png)

---

## Next.js App Router

### Route Structure

QDash uses Next.js 15 App Router with route groups for organization:

```
src/app/
├── (auth)/                     # Protected routes
│   ├── admin/page.tsx          # /admin
│   ├── analysis/page.tsx       # /analysis
│   ├── chat/page.tsx           # /chat
│   ├── chip/
│   │   ├── page.tsx            # /chip
│   │   └── [chipId]/
│   │       └── qubit/
│   │           └── [qubitId]/
│   │               └── page.tsx # /chip/:chipId/qubit/:qubitId
│   ├── execution/
│   │   ├── page.tsx            # /execution
│   │   └── [executionId]/
│   │       └── page.tsx        # /execution/:executionId
│   ├── files/page.tsx          # /files
│   ├── inbox/page.tsx          # /inbox (default landing page)
│   ├── issues/
│   │   ├── page.tsx            # /issues
│   │   └── [issueId]/
│   │       └── page.tsx        # /issues/:issueId
│   ├── metrics/page.tsx        # /metrics
│   ├── provenance/page.tsx     # /provenance
│   ├── settings/page.tsx       # /settings
│   ├── task-results/page.tsx   # /task-results
│   ├── tasks/page.tsx          # /tasks
│   └── workflow/
│       ├── page.tsx            # /workflow
│       ├── new/page.tsx        # /workflow/new
│       └── [name]/page.tsx     # /workflow/:name
├── (public)/                   # Public routes
│   └── login/page.tsx          # /login
├── api/                        # API route handlers (SSE streaming)
├── globals.css                 # Global styles
├── layout.tsx                  # Root layout
├── page.tsx                    # / (redirects to /inbox)
└── providers.tsx               # Provider composition
```

### Route Groups

Route groups (parenthesized folders) organize routes without affecting URLs:

```tsx
// (auth) group - requires authentication
// File: src/app/(auth)/inbox/page.tsx
// URL: /inbox (not /auth/inbox)

// (public) group - no authentication required
// File: src/app/(public)/login/page.tsx
// URL: /login (not /public/login)
```

### Layout Hierarchy

```
RootLayout (src/app/layout.tsx)
├── Providers (QueryClient, Theme, Auth, Project)
└── AppLayout (Navbar, Sidebar)
    ├── (auth) routes → Protected content
    └── (public) routes → Public content
```

---

## Component Architecture

### Component Categories

```
components/
├── ui/                     # Generic, reusable components
│   ├── Card.tsx            # Card container
│   ├── DataTable.tsx       # Generic data table
│   ├── LoadingSpinner.tsx  # Loading indicator
│   ├── FluentEmoji.tsx     # Fluent Emoji component
│   ├── EmptyState.tsx      # Empty state templates
│   └── ...                 # Other UI primitives
│
├── charts/                 # Visualization components
│   ├── Plot.tsx            # Lightweight Plotly wrapper (plotly.js-basic-dist)
│   ├── PlotCard.tsx        # Reusable plot container
│   └── TaskFigure.tsx      # Task result figure
│
├── features/               # Feature-specific components
│   ├── admin/              # Admin page components
│   ├── analysis/           # Analysis page components
│   ├── chat/               # Copilot chat components
│   ├── chip/               # Chip page components
│   ├── execution/          # Execution page components
│   ├── files/              # File management components
│   ├── flow/               # Flow editor components
│   ├── inbox/              # Inbox components
│   ├── issues/             # Issue tracking components
│   ├── metrics/            # Metrics dashboard components
│   ├── provenance/         # Data provenance components
│   ├── qubit/              # Qubit detail components
│   ├── settings/           # Settings page components
│   ├── task-results/       # Task result components
│   └── tasks/              # Task management components
│
├── layout/                 # Layout components
│   ├── AppLayout.tsx       # Main app layout
│   └── AnalysisSidebar.tsx # Analysis page sidebar
│
└── selectors/              # Selection/input components
    ├── ChipSelector/       # Chip dropdown
    ├── DateSelector/       # Date selection
    ├── ParameterSelector/  # Parameter selection
    ├── TagSelector/        # Tag selection
    └── TaskSelector/       # Task selection
```

### Component Responsibility

| Category     | Responsibility         | Reusability                     |
| ------------ | ---------------------- | ------------------------------- |
| `ui/`        | Generic UI primitives  | High - used across all features |
| `charts/`    | Data visualization     | Medium - used in multiple pages |
| `features/`  | Feature-specific logic | Low - specific to one feature   |
| `layout/`    | Page structure         | High - used in all pages        |
| `selectors/` | Data selection         | Medium - used across features   |

---

## Data Flow

### Server State Flow (TanStack Query)

The server state flow (Component → TanStack Query → API Client → Axios → API) is shown in the UI Architecture diagram above.

### Mutation Flow

```tsx
// Component triggers mutation
const mutation = useMutation({
  mutationFn: (data: UpdateChipRequest) => updateChip(chipId, data),
  onSuccess: () => {
    // Invalidate related queries to refetch fresh data
    queryClient.invalidateQueries({ queryKey: ["chips"] });
    toast.success("Chip updated successfully");
  },
  onError: (error) => {
    toast.error(`Failed to update: ${error.message}`);
  },
});

// User action triggers mutation
<button onClick={() => mutation.mutate(formData)}>Save Changes</button>;
```

### Query Key Strategy

```tsx
// Hierarchical keys for granular cache control
["chips"][("chips", chipId)][("chips", chipId, "qubits")][ // All chips // Single chip // Qubits for a chip
  ("chips", chipId, "qubits", qid)
]; // Single qubit

// Invalidation cascades
queryClient.invalidateQueries({ queryKey: ["chips"] });
// Invalidates: ["chips"], ["chips", "X"], ["chips", "X", "qubits"], etc.

queryClient.invalidateQueries({ queryKey: ["chips", chipId] });
// Invalidates: ["chips", chipId], ["chips", chipId, "qubits"], etc.
```

---

## Authentication

### Authentication Flow

The authentication flow (User visit → middleware.ts → AuthProvider → API Requests with X-Username header) is shown in the UI Architecture diagram above.

### Middleware Implementation

```tsx
// src/middleware.ts
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const username = request.cookies.get("username");
  const isPublicRoute = request.nextUrl.pathname.startsWith("/login");

  if (!username && !isPublicRoute) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
```

---

## API Client Generation

### Generation Pipeline

The API client generation pipeline (FastAPI → OpenAPI spec → Orval → Generated Code) is shown in the UI Architecture diagram above.

### Orval Configuration

```javascript
// orval.config.cjs
module.exports = {
  "qdash-file-transfomer": {
    output: {
      client: "react-query", // Generate React Query hooks
      mode: "tags-split", // Split by API tags
      target: "./src/client", // Output directory
      schemas: "./src/schemas", // Types output directory
      override: {
        mutator: {
          path: "./src/lib/custom-instance.ts",
          name: "customInstance",
        },
      },
      clean: true, // Clean output before generation
    },
    input: {
      target: "../docs/oas/openapi.json",
    },
  },
};
```

### Custom Axios Instance

```tsx
// src/lib/api/custom-instance.ts
import axios from "axios";

const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:5715",
});

// Add auth header to all requests
apiClient.interceptors.request.use((config) => {
  const username = document.cookie
    .split("; ")
    .find((row) => row.startsWith("username="))
    ?.split("=")[1];

  if (username) {
    config.headers["X-Username"] = username;
  }
  return config;
});

export const customInstance = <T>(config: AxiosRequestConfig): Promise<T> => {
  return apiClient(config).then((response) => response.data);
};
```

---

## State Management Patterns

### State Categories

| State Type      | Tool           | Use Case                            |
| --------------- | -------------- | ----------------------------------- |
| Server State    | TanStack Query | API data, cached server responses   |
| Client State    | React Context  | Theme, auth, selected project       |
| URL State       | nuqs           | Filters, pagination, selected items |
| Component State | useState       | Form inputs, UI toggles             |

### Pattern: Query + URL State

```tsx
import { useQuery } from "@tanstack/react-query";
import { useQueryState, parseAsString } from "nuqs";

export function ChipListPage() {
  // URL state for filters (persisted in URL)
  const [search, setSearch] = useQueryState(
    "search",
    parseAsString.withDefault(""),
  );
  const [status, setStatus] = useQueryState(
    "status",
    parseAsString.withDefault("all"),
  );

  // Server state with filters
  const { data, isLoading } = useQuery({
    queryKey: ["chips", { search, status }],
    queryFn: () => getChipList({ search, status }),
  });

  return (
    <div>
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search chips..."
      />
      <select value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="all">All</option>
        <option value="active">Active</option>
        <option value="inactive">Inactive</option>
      </select>
      <ChipList chips={data?.chips ?? []} isLoading={isLoading} />
    </div>
  );
}
```

### Pattern: Context for Global State

```tsx
// contexts/ProjectContext.tsx
export function ProjectProvider({ children }: { children: ReactNode }) {
  const [selectedProject, setSelectedProject] = useState<string | null>(null);

  // Persist to localStorage
  useEffect(() => {
    const saved = localStorage.getItem("selectedProject");
    if (saved) setSelectedProject(saved);
  }, []);

  useEffect(() => {
    if (selectedProject) {
      localStorage.setItem("selectedProject", selectedProject);
    }
  }, [selectedProject]);

  return (
    <ProjectContext.Provider value={{ selectedProject, setSelectedProject }}>
      {children}
    </ProjectContext.Provider>
  );
}
```

---

## Key Components

### AppLayout

The main layout component providing consistent structure:

```tsx
// components/layout/AppLayout.tsx
export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-base-200">
      <Navbar />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
```

### DataTable

Generic table component with sorting and filtering:

```tsx
// components/ui/DataTable.tsx
interface DataTableProps<T> {
  data: T[];
  columns: ColumnDefinition<T>[];
  onRowClick?: (row: T) => void;
  isLoading?: boolean;
  emptyMessage?: string;
}

export function DataTable<T>({
  data,
  columns,
  onRowClick,
  isLoading,
  emptyMessage = "No data available",
}: DataTableProps<T>) {
  // Sorting, filtering, pagination logic
  // ...
}
```

### ChipSelector

Reusable chip selection component:

```tsx
// components/selectors/ChipSelector.tsx
interface ChipSelectorProps {
  value: string | null;
  onChange: (chipId: string) => void;
  disabled?: boolean;
}

export function ChipSelector({ value, onChange, disabled }: ChipSelectorProps) {
  const { data } = useQuery({
    queryKey: ["chips"],
    queryFn: () => getChipList(),
  });

  return (
    <select
      className="select select-bordered"
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
    >
      <option value="">Select a chip...</option>
      {data?.chips.map((chip) => (
        <option key={chip.chip_id} value={chip.chip_id}>
          {chip.chip_id}
        </option>
      ))}
    </select>
  );
}
```

