# UI Development

The QDash UI owns browser routes, interaction, visualization, and client-side access to the API.
It uses the generated API client instead of handwritten request functions.

## Choose the Right Guide

| Goal | Read |
| --- | --- |
| Understand routes, layouts, data flow, and global state | [UI Architecture](./architecture.md) |
| Place and name files or run UI tooling | [UI Development Guidelines](./guidelines.md) |
| Choose component and state boundaries | [Components and State](./components.md) |
| Apply Tailwind and DaisyUI | [Styling](./styling.md) |
| Apply icons, colors, loading, feedback, and accessibility rules | [UI Design Policy](./design-policy.md) |
| Write strict TypeScript | [TypeScript](./typescript.md) |
| Call the API and regenerate clients | [API Integration](./api-integration.md) |
| Test, type-check, lint, and build | [UI Testing Guidelines](./testing.md) |

## Source and Tests

Routes live in `ui/src/app/`, feature components in `ui/src/components/features/`, reusable UI
primitives in `ui/src/components/ui/`, and server-state hooks in the generated client or focused
hooks. Keep route files thin and move substantial page content into feature components.

Run `task test-ui` for UI unit tests. Use `task build` for the full build, type, lint, format, and
unused-code checks before a broad UI change is complete.
