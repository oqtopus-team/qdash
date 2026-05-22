# AI Review Evaluation Loop

AI review tuning is easiest when you can replay the production path against a fixed task result, then choose whether to keep the original context or rebuild it from current task knowledge and loaders.

QDash now provides a small replay workflow under `qdash.copilot.evals.ai_review` for that purpose.

## What It Solves

The production AI review path is triggered from two places:

- workflow-side automatic note attachment during calibration execution
- API-side bulk or manual AI review requests from the chip/task-result UI

Both paths now share the same rendering helpers in `src/qdash/copilot/review.py`. The evaluation tooling reuses those helpers instead of duplicating the LLM call path.

## Capture A Snapshot

Capture a replayable snapshot from a real task result:

```bash
uv run python -m qdash.copilot.evals.ai_review capture \
  --task-name CheckQubitSpectroscopy \
  --chip-id chip-1 \
  --qid 4 \
  --task-id task-result-id \
  --output /tmp/ai-review-check-qubit-spec.json
```

The snapshot stores:

- task identifiers (`task_name`, `chip_id`, `qid`, `task_id`)
- the resolved `TaskAnalysisContext`
- expected images
- the selected analysis model
- the user message that was sent to the LLM at capture time

## Replay A Snapshot

Replay the saved snapshot with the current `copilot/review.yaml` and current code:

```bash
uv run python -m qdash.copilot.evals.ai_review run \
  --snapshot /tmp/ai-review-check-qubit-spec.json \
  --mode frozen \
  --output-dir /tmp/ai-review-run-1 \
  --print-markdown
```

Replay modes:

- `frozen`: reuse the stored analysis context. This is best for prompt-only or model-only tuning.
- `rebuild`: rebuild the context from the saved task identifiers using the current code and current task knowledge. This is best when editing `docs/task-knowledge/*`, context loaders, or context shaping logic.

Example rebuild run:

```bash
uv run python -m qdash.copilot.evals.ai_review run \
  --snapshot /tmp/ai-review-check-qubit-spec.json \
  --mode rebuild \
  --output-dir /tmp/ai-review-run-2
```

Each replay writes:

- `result.md`: rendered AI review markdown
- `context.json`: the actual context used for that replay
- `report.json`: metadata including source task IDs, prompt text, and selected model

## Tuning Workflow

Use `frozen` mode when you are tuning:

- `analysis.ai_review_message` in `config/copilot/review.yaml`
- model choice or output-token settings
- deterministic formatting or guard behavior

Use `rebuild` mode when you are tuning:

- `docs/task-knowledge/*`
- `TaskKnowledge.to_prompt()` behavior
- Copilot runtime context loaders
- pruning or reshaping of AI review context

## Model Overrides

You can override the replay model without editing `copilot/review.yaml`:

```bash
uv run python -m qdash.copilot.evals.ai_review run \
  --snapshot /tmp/ai-review-check-qubit-spec.json \
  --mode frozen \
  --model-provider openai \
  --model-name gpt-5.1 \
  --max-output-tokens 4096 \
  --output-dir /tmp/ai-review-run-3
```

## Practical Loop

For short prompt/knowledge iteration cycles:

1. Capture one representative snapshot per failure pattern you care about.
2. Replay in `frozen` mode while tuning the review message and formatting.
3. Replay in `rebuild` mode after editing task knowledge or context builders.
4. Compare `result.md` and `context.json` across runs before retrying against the live chip page or workflow trigger.
