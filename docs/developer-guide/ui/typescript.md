# TypeScript

The QDash UI uses strict TypeScript to keep generated API contracts, component props, and state
transitions explicit.

## Compiler Invariants

`ui/tsconfig.json` enables `strict`, `noUnusedLocals`, `noUnusedParameters`, and
`noFallthroughCasesInSwitch`, and it emits no JavaScript. Next.js owns production output.

Run type generation before TypeScript when route types may have changed:

```bash
cd ui
bunx next typegen
bunx tsc --noEmit
```

`task ci-ui` runs both commands in this order.

## Reuse Contract Types

Import API request and response types from `@/schemas`. Import component-specific types from their
owning module. Do not copy a generated interface into a feature directory to make a mismatch
compile.

Use `import type` when an import is erased at runtime:

```ts
import type { ChipSummary, CreateChipRequest } from "@/schemas";
```

## Narrow Unknown Values

Use `unknown` for data whose shape is not established, then narrow it with runtime checks. Use
`Record<string, unknown>` only when the code genuinely accepts arbitrary keys.

Avoid `any`. A third-party boundary that lacks usable types can justify a narrow local assertion,
but the assertion must not spread into component props or feature state.

## Let Generated Hooks Carry Types

Generated query and mutation hooks already type their responses, errors, variables, and callback
arguments. Do not wrap them in an untyped `useQuery` or `useMutation` call merely to rename the
operation.

Add an explicit annotation when data crosses a generic library boundary or when inference loses a
domain constraint. Do not annotate every array callback when its collection is already typed.

## Model Component State Precisely

Use string unions or discriminated unions for finite UI states instead of independent booleans
that can represent impossible combinations. Keep nullable server data distinct from loading and
error status.

Component props use an interface or named type when the shape is reused or represents the public
component API. Callback props describe their argument and return types explicitly.

## Treat Assertions as Boundaries

Prefer a type guard to a broad `as` assertion. When an assertion is unavoidable, keep it at the
deserialization, DOM, or library boundary and return a correctly typed value to the rest of the
feature.

Do not use non-null assertions to hide a state the UI can actually reach. Render the missing,
loading, or error state instead.

See [API Integration](./api-integration.md) for generated hook usage and
[UI Testing](./testing.md#check-types-and-static-rules) for the complete static checks.
