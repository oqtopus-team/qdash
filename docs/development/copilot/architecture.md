# Copilot Architecture

## Overview

QDash Copilot is an AI-powered assistant that helps experimentalists interpret qubit calibration results. It provides two interaction modes:

1. **Analysis Sidebar** -- Task-scoped analysis within the metrics modal, providing contextual interpretation of individual calibration results (e.g., CheckT1, CheckRabi).
2. **Chat Page** -- A dedicated chat interface for chip-wide questions, cross-qubit comparisons, and exploratory data analysis.

Both modes use the same underlying LLM agent with tool-calling capabilities, sandboxed Python execution, and SSE streaming for real-time progress feedback.

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js)                                             │
│                                                                 │
│  ┌─────────────────────┐     ┌──────────────────────────┐      │
│  │ CopilotChatPage     │     │ AnalysisChatPanel        │      │
│  │ (useCopilotChat)    │     │ (useAnalysisChat)        │      │
│  └────────┬────────────┘     └────────────┬─────────────┘      │
│           │                               │                     │
│           │ POST /copilot/chat/stream     │ POST /copilot/      │
│           │ (SSE)                         │   analyze/stream    │
│           │                               │ (SSE)               │
└───────────┼───────────────────────────────┼─────────────────────┘
            │                               │
┌───────────┼───────────────────────────────┼─────────────────────┐
│  Backend (FastAPI)                                               │
│           │                               │                     │
│  ┌────────▼───────────────────────────────▼──────────────┐      │
│  │  copilot router (routers/copilot.py)                  │      │
│  │  - SSE event generator                                │      │
│  │  - Queue + Task pattern for progress streaming        │      │
│  │  - Tool executor wiring                               │      │
│  └────────┬──────────────────────────────────────────────┘      │
│           │                                                     │
│  ┌────────▼──────────────┐  ┌───────────────────────────┐      │
│  │  copilot_agent.py     │  │  copilot_sandbox.py       │      │
│  │  - OpenAI Responses   │  │  - AST validation         │      │
│  │    API client         │  │  - Restricted builtins    │      │
│  │  - Tool call loop     │  │  - Resource limits        │      │
│  │  - System prompt      │  │  - exec() with timeout    │      │
│  │    construction       │  └───────────────────────────┘      │
│  └────────┬──────────────┘                                      │
│           │                                                     │
│  ┌────────▼──────────────┐  ┌───────────────────────────┐      │
│  │  OpenAI API           │  │  MongoDB (via Bunnet)     │      │
│  │  (gpt-4.1 default)    │  │  - QubitDocument          │      │
│  │  or Ollama fallback   │  │  - TaskResultHistory      │      │
│  └───────────────────────┘  │  - ChipDocument           │      │
│                              └───────────────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

## Key Files

| File | Responsibility |
|------|---------------|
| `src/qdash/api/routers/copilot.py` | FastAPI router with `/config`, `/analyze`, `/analyze/stream`, `/chat/stream` endpoints; SSE event generation; tool executor wiring |
| `src/qdash/api/lib/copilot_agent.py` | LLM agent: system prompt construction, OpenAI Responses API calls, tool call loop, response parsing |
| `src/qdash/api/lib/copilot_sandbox.py` | Sandboxed Python execution: AST validation, restricted builtins, resource limits |
| `src/qdash/api/lib/copilot_analysis.py` | Pydantic models: `TaskAnalysisContext`, `AnalysisResponse`, `BlocksAnalysisResponse`, request schemas |
| `src/qdash/api/lib/copilot_config.py` | Configuration loader: `CopilotConfig`, `ModelConfig`, `ScoringThreshold` models; YAML loading with local override |
| `src/qdash/datamodel/task_knowledge.py` | `TaskKnowledge` model with domain-specific knowledge per calibration task |
| `config/copilot.yaml` | Main configuration file for model settings, scoring thresholds, system prompts |
| `ui/src/hooks/useCopilotChat.ts` | React hook for the chat page: session management, SSE consumption, localStorage persistence |
| `ui/src/hooks/useAnalysisChat.ts` | React hook for the analysis sidebar: task-scoped SSE streaming, message management |
| `ui/src/components/features/chat/CopilotChatPage.tsx` | Chat page UI: session list, message rendering, blocks/chart display |
| `ui/src/components/features/metrics/AnalysisChatPanel.tsx` | Analysis sidebar UI within the metrics modal |

## Configuration

### `config/copilot.yaml`

```yaml
enabled: true

# Language settings
thinking_language: en      # Internal reasoning language
response_language: ja      # User-facing response language

# Model settings
model:
  provider: openai         # openai | ollama
  name: gpt-4.1
  temperature: 0.7
  max_output_tokens: 2048

# Metrics for chip health evaluation
evaluation_metrics:
  qubit: [qubit_frequency, anharmonicity, t1, t2_echo, ...]
  coupling: [zx90_gate_fidelity, bell_state_fidelity]

# Scoring thresholds per metric
scoring:
  t1:
    good: 50
    excellent: 100
    bad: 20
    unit: "μs"
    higher_is_better: true
  # ... (see config/copilot.yaml for full list)

# Task analysis settings
analysis:
  enabled: true
  multimodal: true
  max_conversation_turns: 10
```

Configuration is loaded via `ConfigLoader` with local override support (`copilot.local.yaml`).

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI API authentication |
| `OLLAMA_URL` | Ollama server URL (default: `http://localhost:11434`) |
| `NEXT_PUBLIC_API_URL` | API base URL for frontend (default: `/api`) |

## Two Modes

### Analysis Sidebar

Activated from the metrics modal when viewing a specific task result (e.g., CheckT1 for qubit Q03).

- **Endpoint**: `POST /copilot/analyze/stream`
- **Hook**: `useAnalysisChat`
- **Context**: Full `TaskAnalysisContext` including task knowledge, qubit parameters, experiment results, historical data, neighbor qubit data, and coupling parameters
- **Use case**: "Is this T1 result normal?", "Why does the fit R² look low?"

### Chat Page

A standalone page (`/copilot`) for general questions about the calibration system.

- **Endpoint**: `POST /copilot/chat/stream`
- **Hook**: `useCopilotChat`
- **Context**: Chip ID, optional qubit ID, scoring thresholds
- **Use case**: "Compare T1 across all qubits", "Show me the frequency trend for Q16"
- **Sessions**: Persisted to localStorage with multi-session support
