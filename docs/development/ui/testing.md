# UI Testing Guidelines for QDash

This document provides guidelines for testing the QDash frontend application. It covers testing strategies, tools, and best practices.

## Table of Contents

1. [Testing Strategy](#testing-strategy)
2. [Manual Testing](#manual-testing)
3. [Type Checking](#type-checking)
4. [Linting](#linting)
5. [Build Verification](#build-verification)
6. [Component Testing Patterns](#component-testing-patterns)
7. [Testing Checklist](#testing-checklist)

---

## Testing Strategy

### Current Testing Approach

QDash UI currently uses a combination of:

1. **Static Analysis** - TypeScript type checking and ESLint
2. **Build Verification** - Production build validation
3. **Manual Testing** - Feature testing in development environment

### Testing Pyramid for QDash UI

```
                    ┌───────────────────┐
                    │   E2E Tests       │  ← Future: Playwright/Cypress
                    │   (Manual now)    │
                    └─────────┬─────────┘
                              │
               ┌──────────────┴──────────────┐
               │     Integration Tests       │  ← Future: Testing Library
               │     (Component + API)       │
               └──────────────┬──────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        │            Static Analysis                 │  ← Current
        │    TypeScript + ESLint + Build Check      │
        └───────────────────────────────────────────┘
```

---

## Manual Testing

### Development Server

```bash
# Start development server
cd ui
bun run dev

# Access at http://localhost:3000
```

### Testing Workflow

1. **Start the full stack**

   ```bash
   # From project root
   docker compose up -d

   # Or start UI separately for faster iteration
   cd ui && bun run dev
   ```

2. **Test each page manually**
   - Navigate to each route
   - Verify data loads correctly
   - Test user interactions
   - Check error states
   - Verify responsive design

### Key Test Scenarios

#### Authentication

- [ ] Login page displays correctly
- [ ] Login redirects to /metrics
- [ ] Protected routes redirect to /login when not authenticated
- [ ] Logout clears session

#### Metrics Page (`/metrics`)

- [ ] Page loads without errors
- [ ] Chip selector works
- [ ] Data visualizations render
- [ ] Time range selection works

#### Chip Page (`/chip`)

- [ ] Chip list loads
- [ ] Chip details page loads
- [ ] Qubit grid displays correctly
- [ ] Task results show properly

#### Flow Page (`/flow`)

- [ ] Flow list loads
- [ ] Create new flow works
- [ ] Flow editor functions
- [ ] Execute flow works

#### Execution Page (`/execution`)

- [ ] Execution list loads
- [ ] Execution details show
- [ ] Real-time updates work (if applicable)

#### Analysis Page (`/analysis`)

- [ ] Charts render correctly
- [ ] Filters work
- [ ] Export functions work

---

## Type Checking

### Running TypeScript Checks

```bash
cd ui

# Full type check
bunx tsc --noEmit

# Watch mode during development
bunx tsc --noEmit --watch
```

### Common Type Errors and Fixes

#### Implicit `any` in Callbacks

```tsx
// ❌ Error: Parameter 'chip' implicitly has an 'any' type
chips.map((chip) => chip.name);

// ✅ Fix: Add explicit type
import type { ChipSummary } from "@/schemas";
chips.map((chip: ChipSummary) => chip.name);
```

#### Mutation Callback Types

```tsx
// ❌ Error: Parameter 'response' implicitly has an 'any' type
onSuccess: (response) => {
  console.log(response.data);
};

// ✅ Fix: Add explicit type
import type { AxiosResponse } from "axios";
import type { ExecuteFlowResponse } from "@/schemas";

onSuccess: (response: AxiosResponse<ExecuteFlowResponse>) => {
  console.log(response.data);
};
```

#### Array Method Types

```tsx
// ❌ Error in .reduce(), .filter(), .some(), .find()
tasks.reduce((acc, task) => { ... }, {})

// ✅ Fix: Type both accumulator and item
tasks.reduce((acc: Record<string, TaskInfo[]>, task: TaskInfo) => { ... }, {})
```

### Type Check in CI/CD

The Docker build runs type checking in strict mode. To reproduce locally:

```bash
# Clean build (like Docker)
rm -rf .next
bun run build
```

---

## Linting

### Running ESLint

```bash
cd ui

# Check for issues
bun run lint

# Auto-fix issues
bun run fmt
```

### ESLint Configuration

```javascript
// eslint.config.mjs
export default [
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "src/schemas/**", // Auto-generated types
      "src/client/**", // Auto-generated client
    ],
  },
  {
    files: ["**/*.{ts,tsx}"],
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "@typescript-eslint/no-unused-vars": "off",
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
];
```

### Common Lint Issues

#### React Hooks Rules

```tsx
// ❌ Error: Hook called conditionally
function Component({ condition }) {
  if (condition) {
    const [state, setState] = useState(null); // Error!
  }
}

// ✅ Fix: Always call hooks at top level
function Component({ condition }) {
  const [state, setState] = useState(null);

  if (!condition) return null;
  // Use state...
}
```

#### Exhaustive Dependencies

```tsx
// ⚠️ Warning: Missing dependency
useEffect(() => {
  fetchData(userId);
}, []); // Missing 'userId'

// ✅ Fix: Add dependency
useEffect(() => {
  fetchData(userId);
}, [userId]);

// Or if intentional, disable with comment
useEffect(() => {
  // Run only on mount
  fetchData(userId);
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

---

## Build Verification

### Production Build

```bash
cd ui

# Build for production
bun run build

# Start production server
bun run start
```

### Build Checks

The build process includes:

1. **Compilation** - TypeScript to JavaScript
2. **Type Checking** - Full TypeScript validation
3. **Linting** - ESLint checks
4. **Optimization** - Tree shaking, minification
5. **Static Generation** - Pre-render static pages

### CI/CD Build

```bash
# Docker build (strict mode)
docker compose build ui

# This is equivalent to:
cd ui
rm -rf .next
bun install
bun run build
```

### Build Output Analysis

After building, check the output:

```
Route (app)                              Size     First Load JS
┌ ○ /                                    143 B          87.7 kB
├ ○ /admin                               7.71 kB         123 kB
├ ○ /analysis                            13.6 kB         171 kB
├ ○ /chip                                10.3 kB         172 kB
├ ƒ /chip/[chipId]/qubit/[qubitsId]      1.34 MB        1.52 MB  ← Large!
...
```

Monitor for:

- Large bundle sizes (> 500KB first load)
- Missing routes
- Build errors

---

## Component Testing Patterns

### Testing with React Testing Library (Future)

While not currently implemented, here are patterns for future testing:

#### Basic Component Test

```tsx
// __tests__/components/ChipCard.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChipCard } from "@/components/ui/ChipCard";

describe("ChipCard", () => {
  const mockChip = {
    chip_id: "chip-001",
    status: "active",
  };

  it("renders chip information", () => {
    render(<ChipCard chip={mockChip} onSelect={jest.fn()} />);

    expect(screen.getByText("chip-001")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
  });

  it("calls onSelect when clicked", async () => {
    const onSelect = jest.fn();
    render(<ChipCard chip={mockChip} onSelect={onSelect} />);

    await userEvent.click(screen.getByRole("button"));

    expect(onSelect).toHaveBeenCalledWith("chip-001");
  });
});
```

#### Testing with React Query

```tsx
// __tests__/components/ChipList.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChipList } from "@/components/features/chip/ChipList";

// Mock API
jest.mock("@/client/chip/chip", () => ({
  getChipList: jest.fn().mockResolvedValue({
    chips: [
      { chip_id: "chip-001", status: "active" },
      { chip_id: "chip-002", status: "inactive" },
    ],
  }),
}));

describe("ChipList", () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  const wrapper = ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  it("renders chips from API", async () => {
    render(<ChipList />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("chip-001")).toBeInTheDocument();
      expect(screen.getByText("chip-002")).toBeInTheDocument();
    });
  });
});
```

#### Testing Hooks

```tsx
// __tests__/hooks/useTimeRange.test.ts
import { renderHook, act } from "@testing-library/react";
import { useTimeRange } from "@/hooks/useTimeRange";

describe("useTimeRange", () => {
  it("returns default time range", () => {
    const { result } = renderHook(() => useTimeRange());

    expect(result.current.startDate).toBeDefined();
    expect(result.current.endDate).toBeDefined();
  });

  it("updates time range", () => {
    const { result } = renderHook(() => useTimeRange());
    const newStart = new Date("2024-01-01");

    act(() => {
      result.current.setStartDate(newStart);
    });

    expect(result.current.startDate).toEqual(newStart);
  });
});
```

---

## Testing Checklist

### Before Committing

- [ ] `bunx tsc --noEmit` passes
- [ ] `bun run lint` passes (or warnings < 15)
- [ ] `bun run build` succeeds

### Before Pull Request

- [ ] All type errors fixed
- [ ] No new lint errors introduced
- [ ] Manual testing completed for changed features
- [ ] Build succeeds locally
- [ ] Responsive design checked (if UI changes)

### Before Release

- [ ] Full manual test of all pages
- [ ] Docker build succeeds
- [ ] Performance check (bundle sizes)
- [ ] Cross-browser testing (Chrome, Firefox, Safari)
- [ ] Mobile responsiveness verified

---

## Debugging Tips

### React Query DevTools

Add DevTools during development:

```tsx
// src/app/providers.tsx
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";

export function Providers({ children }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
```

### Network Tab Debugging

1. Open Chrome DevTools → Network tab
2. Filter by "Fetch/XHR"
3. Check request/response for API calls
4. Verify headers (X-Username)

### Console Debugging

```tsx
// Add temporary logging
const { data, isLoading, error } = useQuery({
  queryKey: ["chips"],
  queryFn: async () => {
    console.log("Fetching chips...");
    const result = await getChipList();
    console.log("Got chips:", result);
    return result;
  },
});
```

### React Developer Tools

Install React DevTools browser extension to:

- Inspect component tree
- View props and state
- Profile rendering performance

---

## Summary

### Testing Commands Quick Reference

| Command             | Purpose                                |
| ------------------- | -------------------------------------- |
| `bunx tsc --noEmit` | Type checking                          |
| `bun run lint`      | ESLint checks                          |
| `bun run fmt`       | Auto-fix lint issues                   |
| `bun run build`     | Production build (includes type check) |
| `bun run dev`       | Development server for manual testing  |

### Key Testing Principles

1. **Type Safety First** - TypeScript catches most issues at compile time
2. **Build Verification** - Production build must pass before merging
3. **Manual Testing** - Test user flows for changed features
4. **Progressive Enhancement** - Add automated tests as the codebase grows
