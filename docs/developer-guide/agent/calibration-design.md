# Calibration Design

Agents choose experiments and interpret evidence; QDash controls execution, authority, and
accepted calibration state. This division guides changes to SDKs, tools, skills, and workers.
The [Agent Platform](./agent-platform.md) describes the enforced session contract.

<Diagram name="calibration-reasoning-boundary" caption="The agent prepares experiments with Code Mode; QDash authorizes operations and records evidence for the next decision." />

## Separate measurement, assessment, and adoption

A measurement produces evidence. An assessment interprets it. Adoption commits an accepted
candidate; applying backend configuration and configuring hardware are further operations.
Keep these effects explicit in tool interfaces and approval descriptions.

For example, “measure T1 again” should propose measurement authority without parameter-update
authority. “Tune the frequency and use it for Rabi” can require an approved frequency update
before the dependent measurement. This is a rule for agent behavior, not a guarantee that a
model always infers the user's intent correctly. Server grants remain the enforcement boundary.

An agent session grants bounded work once so the agent can proceed without a dialog for every
step. Request authority needed for the objective, and stop or request a new scope when it is
insufficient. Expert guidance provides evidence; it does not enlarge the grant. See
[approval and dependent steps](./agentic-calibration.md#approval).

## Share experiment definitions across languages

Python and TypeScript describe the same targets, task calls, steps, and sweeps through the
version 2 [pipeline spec](../workflow/calibration-pipeline.md). SDK builders make those definitions
convenient to compose; JSON carries their meaning to the server. Constructing a definition
performs no measurement and grants no authority.

Keep declarative definitions independent of worker imports and client credentials. Compare both
SDKs against shared serialization cases and server validation. This contract covers valid typed
inputs, not identical language-specific coercion or exception behavior. See the
[TypeScript definition contract](../../reference/clients/typescript.md#define-a-calibration).
New measurement implementations and Python scientific computation belong in worker tasks or
saved workflows; definition parity does not execute arbitrary Python in JavaScript.

## Use code to prepare experiments

Code Mode combines authorized reads, computes comparisons, and constructs and validates specs.
Its `qdash.calibration` namespace uses the SDK's pure builders. Calculation and tool feedback
let an agent correct an experiment proposal before execution. A successful calculation is
supporting evidence, not an authoritative task result or permission to commit a value.

Prefer Code Mode when preparation requires several tool results, filtering, or repeated
construction. Keep intermediate data in code and return the evidence needed for the next
judgment. A single lookup can use its tool directly; using Code Mode is not an objective itself.

This choice has three complementary sources:

- Pi's [“You Said No MCP!”](https://earendil.com/posts/you-said-no-mcp/) explains its design:
  discoverable tools return structured data that an agent composes in a JavaScript sandbox.
  This supports QDash's choice of reusable tools and pure builders rather than a separate
  tool for every combination of tasks.
- [CodeAct (Wang et al., ICML 2024)](https://proceedings.mlr.press/v235/wang24h.html)
  evaluates executable Python actions against text and JSON actions in tool-use benchmarks.
  Control flow, intermediate variables, and execution feedback support composition and repair.
  Its results motivate this approach; they do not establish calibration quality, fewer physical
  measurements, or an advantage for every model and task.
- Anthropic's engineering article
  [“Code execution with MCP”](https://www.anthropic.com/research/code-execution-with-mcp)
  describes loading tools on demand and processing intermediate data before returning it to
  the model. It motivates reducing context consumption and data copying. It is an implementation
  account, not a QDash benchmark; its reported savings are not expected QDash savings.

Evaluate these benefits on QDash workloads, including correctness, model tokens, latency, and
measurement cost. Keeping Code Mode read-only is QDash's execution-authority decision, not a
requirement or a safety result established by these sources.

Keep measurements, commits, and long waits on their existing direct tool paths. Code Mode
currently permits only audited read-only tool calls. Adding a builder must not widen that set.
The [extension design](./extensions.md#calibration-builders-in-code-mode) explains how both hosts
share the implementation; the [script example](../../reference/pi-qdash.md#scripts-and-deferred-tools)
shows preparation followed by a separate approved execution.

## Choose the execution path by its semantics

Use a pipeline for predetermined task ordering, scheduling, and result filters. Use an agent
session when new evidence requires diagnosis and selection of the next measurement. Deterministic
processing belongs in the execution engine; judgment belongs in the agent loop. A saved Python
workflow can express custom worker-side logic outside the declarative spec.

<Diagram name="calibration-execution-paths" caption="Ordinary pipelines can write task outputs directly. Agent sessions stage candidates and require a separate accepted, authorized commit." />

These paths have different write semantics. Ordinary pipeline calls can update calibration values
directly under their execution approval. Agent-session measurements stage candidates and use
separate acceptance and commit checks. Never substitute an ordinary pipeline for session steps
to bypass those checks. A calibration objective groups runs; it does not authorize them. See
[Calibration Sessions](./calibration-sessions.md).

## Preserve the proposal through approval and execution

The current pipeline tools validate a spec, then accept the spec again in the direct execution
call. Revalidate after edits and present the resolved tasks and settings for approval. Validation
checks feasibility against observed state; it does not reserve hardware or authorize execution.

Binding approval and execution to a stored, validated plan is a design direction, not an
implemented plan-ID execution API. Such a change must preserve the reviewed content and its
provenance while rechecking permissions and relevant state at dispatch. If changed state invalidates
the proposal, return to validation rather than silently changing the approved experiment.

## Recover from authoritative records

Record measurements, assessments, accepted candidates, commits, and backend applications as
distinct evidence. Agent explanations help interpret those records but cannot replace them.
Task completion, deterministic quality gates, and model evaluation also remain distinct.

Continue a session by reading QDash's persisted context. A disconnect or timeout does not prove
that a measurement stopped. Reconcile an uncertain dispatch before proposing another measurement;
reuse the existing identity where the operation's retry contract allows it. See
[the model-driven loop](./agentic-calibration.md#the-model-driven-loop) and
[run recovery](./calibration-sessions.md).

## Evaluate outcomes and boundaries

Judge success from recorded operations and results, including unnecessary measurements, requested
update authority, incorrect commits, appropriate escalation, and recovery after interruption.
Fewer model turns are useful only when experiment quality and execution guarantees hold.

Use shared SDK fixtures and both-host sandbox tests for definitions and tool boundaries. Use
[real-model fake-loop validation](./agent-validation.md) for action selection, approval handling,
and record consistency. Include measurement-only requests, dependent updates, failed-target
filters, and uncertain outcomes. Distinguish spontaneous behavior from explicitly guided trials,
and record the actual model and service revisions. Fake-backend success does not establish
hardware safety or scientific accuracy.
