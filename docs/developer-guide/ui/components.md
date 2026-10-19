# Components and State

How QDash components are organized and written, and which tool holds each kind of state. The visual rules (icons, colors, empty and loading states) are in [design-policy.md](./design-policy.md); the data-flow diagrams are in [architecture.md](./architecture.md).

## Component Design

### DaisyUI and Radix Responsibilities

QDash uses DaisyUI and Radix UI together rather than migrating wholesale from one to the other.

- Use DaisyUI for the visual system: buttons, cards, form controls, badges, tables, loading states, themes, and semantic colors.
- Use an established Radix-based component from `ui/src/components/ui/` when an interaction needs focus trapping or restoration, keyboard navigation, portals, outside-click or Escape dismissal, or collision-aware positioning.
- Style Radix primitives with Tailwind and DaisyUI semantic colors so they remain consistent across light and dark themes.
- Reuse `Dialog` and `DropdownMenu` instead of importing Radix packages directly in feature components.
- Do not add a new headless primitive merely to replace a working DaisyUI visual component. Confirm that the interaction has behavioral or accessibility requirements first.

Typical choices:

| UI need | Preferred foundation |
| ------- | -------------------- |
| Button, card, input, badge, table | DaisyUI |
| Modal dialog | Shared Radix `Dialog` primitive |
| Action or multi-select menu | Shared Radix `DropdownMenu` primitive |
| Page-specific spacing and layout | Tailwind CSS |
| Select, popover, tooltip, or collapsible | Evaluate behavior first; introduce a shared headless primitive only when needed |

The same rule from the design side: [design-policy.md](./design-policy.md#interaction-and-visual-layers).

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
// Good - Clear structure with types
import { useState } from "react";
import type { ChipData } from "@/schemas";

interface ChipCardProps {
  chip: ChipData;
  onSelect: (chipId: string) => void;
  isSelected?: boolean;
}

export function ChipCard({
  chip,
  onSelect,
  isSelected = false,
}: ChipCardProps) {
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
// Good - Explicit interface
interface DataTableProps {
  data: Record<string, unknown>[];
  columns: ColumnDefinition[];
  onRowClick?: (row: Record<string, unknown>) => void;
  isLoading?: boolean;
}

export function DataTable({
  data,
  columns,
  onRowClick,
  isLoading = false,
}: DataTableProps) {
  // ...
}

// Bad - Inline types or any
export function DataTable({ data, columns }: { data: any; columns: any }) {
  // ...
}
```

---

## State Management

### Form State and Validation

Use React Hook Form with Zod for forms that have validation, multiple fields, or submission value
normalization. Keep UI-only state such as password visibility outside the form. Prefer field-level error
messages connected with `aria-describedby`; reserve alerts and toasts for submission or server errors.

Simple search fields, toggles, and single-value controls do not need a form library.

### Server State with TanStack Query

Use TanStack Query for all API data fetching:

```tsx
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getChipList, updateChip } from "@/client/chip/chip";

// Good - Query with proper typing
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

// Good - Mutation with cache invalidation
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
// Good - Hierarchical query keys
queryKey: ["chips"]; // All chips
queryKey: ["chips", chipId]; // Specific chip
queryKey: ["chips", chipId, "qubits"]; // Qubits for a chip
queryKey: ["chips", chipId, "qubits", qid]; // Specific qubit

// Good - With filters
queryKey: ["tasks", { chipId, status: "active" }];
```

How invalidation cascades through hierarchical keys: [architecture.md](./architecture.md#query-key-strategy).

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

The variant that persists the selection to `localStorage`: [architecture.md](./architecture.md#pattern-context-for-global-state).

### URL State with nuqs

Use `nuqs` for URL-synchronized state:

```tsx
import { useQueryState, parseAsString, parseAsInteger } from "nuqs";

export function FilteredList() {
  // State synced to URL: ?search=foo&page=2
  const [search, setSearch] = useQueryState(
    "search",
    parseAsString.withDefault(""),
  );
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
