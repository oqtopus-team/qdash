# API Integration

How UI code calls the backend: through the Orval-generated client and its TanStack Query hooks. The generation pipeline and the custom Axios instance are described in [architecture.md](./architecture.md#api-client-generation).

## Auto-Generated Client

API client code is auto-generated from OpenAPI spec. **Never edit files in `src/client/` or `src/schemas/`**.

```bash
# Regenerate API client
task generate
```

## Using Generated Hooks

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

## Type Annotations for Callbacks

Always add explicit type annotations for mutation callbacks:

```tsx
import { useMutation } from "@tanstack/react-query";
import { executeFlow } from "@/client/flow/flow";
import type { ExecuteFlowResponse } from "@/schemas";
import type { AxiosResponse } from "axios";

// Good - Explicit types for callbacks
const mutation = useMutation({
  mutationFn: () => executeFlow(flowName),
  onSuccess: (response: AxiosResponse<ExecuteFlowResponse>) => {
    console.log("Execution started:", response.data.execution_id);
  },
  onError: (error: Error) => {
    console.error("Failed to execute:", error.message);
  },
});

// Bad - Implicit any types
const mutation = useMutation({
  mutationFn: () => executeFlow(flowName),
  onSuccess: (response) => {
    // 'response' implicitly has 'any' type
    console.log(response.data.execution_id);
  },
});
```

## Array Method Type Annotations

Add type annotations to array callbacks to avoid implicit `any`:

```tsx
import type { TaskInfo, ChipSummary } from "@/schemas";

// Good - Explicit types
const activeChips = chips.filter(
  (chip: ChipSummary) => chip.status === "active",
);
const chipNames = chips.map((chip: ChipSummary) => chip.chip_id);
const hasTask = tasks.some((task: TaskInfo) => task.name === targetName);

// Bad - Implicit any
const activeChips = chips.filter((chip) => chip.status === "active");
```

The compiler errors these rules prevent, with fixes: [testing.md](./testing.md#common-type-errors-and-fixes).
