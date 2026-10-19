# TypeScript

Type rules for `ui/` code; the compiler runs in strict mode and the Docker build fails on any implicit `any`. How to run the checks and fix the common errors: [testing.md](./testing.md#type-checking).

## Strict Mode

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

## Import Types

Use `import type` for type-only imports:

```tsx
// Good - Type-only import
import type { ChipSummary, TaskInfo } from "@/schemas";
import type { AxiosResponse } from "axios";

// Regular import for values
import { useQuery } from "@tanstack/react-query";
```

## Avoid `any`

Never use `any` type. Use proper types or `unknown` with type guards:

```tsx
// Good
function processData(data: Record<string, unknown>) {
  if (typeof data.name === "string") {
    console.log(data.name);
  }
}

// Bad
function processData(data: any) {
  console.log(data.name);
}
```

## Type Assertions

Prefer type guards over type assertions:

```tsx
// Good - Type guard
function isChipData(data: unknown): data is ChipData {
  return typeof data === "object" && data !== null && "chip_id" in data;
}

if (isChipData(response)) {
  console.log(response.chip_id);
}

// Bad - Type assertion
const chip = response as ChipData; // Unsafe
```

Callback and array-method parameters need explicit annotations too; see [api-integration.md](./api-integration.md#type-annotations-for-callbacks).
