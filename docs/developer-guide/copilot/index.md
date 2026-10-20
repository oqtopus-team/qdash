# Copilot Development

The Copilot subsystem owns project-aware chat, calibration evaluation, agent execution,
knowledge integration, streaming, and restricted analysis tools.

## Choose the Right Guide

| Goal | Read |
| --- | --- |
| Understand the chat runtime and interaction modes | [Copilot Architecture](./architecture.md) |
| Understand the safety boundary for calibration agents | [Agent Platform](./agent-platform.md) |
| Change task knowledge or agent instructions | [Copilot Knowledge Layout](./knowledge-layout.md) |
| Change recorded calibration evaluation | [Calibration Evaluation](./evaluation.md) |
| Change restricted Python analysis | [Sandboxed Python Execution](./sandbox.md) |
| Stream runtime progress to the UI | [SSE Streaming](./streaming.md) |
| Keep large tool results out of model context | [Tool Result Compression](./tool-result-compression.md) |
| Apply reusable LLM integration patterns | [LLM Integration Patterns](./llm-integration-patterns.md) |

User procedures for chat and agent-driven runs are in [Copilot](../../user-guide/copilot.md) and
[Agent Calibration](../../user-guide/agent-calibration.md).
