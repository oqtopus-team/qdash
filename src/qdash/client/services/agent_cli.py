"""Command-line entry point for user-operated QDash calibration agents."""

from __future__ import annotations

import argparse
import json
from typing import Any

from qdash.client.services.agent_runner import (
    AgentCalibrationRunner,
    AgentCampaignNode,
    AgentCampaignOutcome,
    AgentCampaignRunner,
    AgentStepOutcome,
)
from qdash.client.services.client import QDashClient as QDashClient  # noqa: PLC0414


def _json_object(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("value must be a JSON object")
    return parsed


def _campaign_plan(value: str) -> list[AgentCampaignNode]:
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not parsed:
        raise argparse.ArgumentTypeError("campaign plan must be a non-empty JSON array")

    allowed_keys = {
        "task_name",
        "candidate_parameter",
        "id",
        "on_pass",
        "on_rollback",
        "parameter_overrides",
        "diagnosis",
        "reconfigure_before_task",
        "commit_candidate",
        "apply_backend",
        "push_to_github",
    }
    nodes: list[AgentCampaignNode] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise argparse.ArgumentTypeError(f"campaign node {index} must be a JSON object")
        unknown = sorted(set(item) - allowed_keys)
        if unknown:
            raise argparse.ArgumentTypeError(
                f"campaign node {index} has unknown fields: {', '.join(unknown)}"
            )
        task_name = item.get("task_name")
        candidate_parameter = item.get("candidate_parameter")
        if not isinstance(task_name, str) or not isinstance(candidate_parameter, str):
            raise argparse.ArgumentTypeError(
                f"campaign node {index} requires string task_name and candidate_parameter"
            )
        node_id = item.get("id")
        on_pass = item.get("on_pass")
        on_rollback = item.get("on_rollback")
        if any(
            value is not None and not isinstance(value, str)
            for value in (node_id, on_pass, on_rollback)
        ):
            raise argparse.ArgumentTypeError(f"campaign node {index} graph fields must be strings")
        diagnosis = item.get("diagnosis", "")
        overrides = item.get("parameter_overrides", {})
        if not isinstance(diagnosis, str) or not isinstance(overrides, dict):
            raise argparse.ArgumentTypeError(
                f"campaign node {index} diagnosis must be a string and overrides an object"
            )
        bool_fields = (
            "reconfigure_before_task",
            "commit_candidate",
            "apply_backend",
            "push_to_github",
        )
        if any(not isinstance(item.get(name, False), bool) for name in bool_fields):
            raise argparse.ArgumentTypeError(f"campaign node {index} flags must be booleans")
        try:
            if any(
                not isinstance(key, str)
                or isinstance(raw, bool)
                or not isinstance(raw, (int, float))
                for key, raw in overrides.items()
            ):
                raise ValueError("parameter overrides must contain numeric values")
            numeric_overrides = {str(key): float(raw) for key, raw in overrides.items()}
            nodes.append(
                AgentCampaignNode(
                    task_name=task_name,
                    candidate_parameter=candidate_parameter,
                    node_id=node_id,
                    on_pass=on_pass,
                    on_rollback=on_rollback,
                    parameter_overrides=numeric_overrides,
                    diagnosis=diagnosis,
                    **{name: item.get(name, False) for name in bool_fields},
                )
            )
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(f"invalid campaign node {index}: {exc}") from exc
    return nodes


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qdash-agent",
        description="Run bounded calibration-agent operations through QDash.",
    )
    auth = parser.add_mutually_exclusive_group()
    auth.add_argument("--profile", help="QDash config profile name (default: default)")
    auth.add_argument(
        "--from-env",
        action="store_true",
        help="Load QDash connection settings from QDASH_* environment variables",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start-session", help="Create a bounded agent session")
    start.add_argument("--chip-id", required=True)
    start.add_argument("--qid", action="append", required=True, dest="qids")
    start.add_argument("--task", action="append", required=True, dest="tasks")
    start.add_argument(
        "--allowed-overrides",
        required=True,
        type=_json_object,
        help='JSON bounds, e.g. {"t1":{"minimum":1,"maximum":500}}',
    )
    start.add_argument(
        "--quality-gates",
        type=_json_object,
        default={},
        help='JSON quality bounds, e.g. {"r2":{"minimum":0.9}}',
    )
    start.add_argument("--max-actions", type=int, default=100)
    start.add_argument(
        "--allow-reconfigure",
        action="store_true",
        help="Authorize explicit hardware Configure before an agent task",
    )
    start.add_argument("--expires-in-seconds", type=int, default=21_600)
    start.add_argument("--skill-name", default="")
    start.add_argument("--skill-version", default="")
    start.add_argument("--skill-hash", default="")
    start.add_argument("--model-name", default="")

    step = commands.add_parser("run-step", help="Run one staged Skill measurement node")
    step.add_argument("--session-id", required=True)
    step.add_argument("--task", required=True)
    step.add_argument("--qid", required=True)
    step.add_argument("--source-execution-id", required=True)
    step.add_argument("--candidate-parameter", required=True)
    step.add_argument(
        "--parameter-overrides",
        type=_json_object,
        default={},
        help="JSON calibration input parameter overrides",
    )
    step.add_argument("--diagnosis", default="")
    step.add_argument(
        "--reconfigure-before-task",
        action="store_true",
        help="Run Configure before the requested task when the session allows it",
    )
    step.add_argument("--commit", action="store_true", dest="commit_candidate")
    step.add_argument(
        "--apply-backend",
        action="store_true",
        help="Apply the committed candidate on a worker and verify mapped backend files",
    )
    step.add_argument(
        "--github-push",
        action="store_true",
        dest="push_to_github",
        help="Version changed backend files in GitHub",
    )
    step.add_argument("--action-idempotency-key")
    step.add_argument("--commit-idempotency-key")
    step.add_argument("--backend-apply-idempotency-key")
    step.add_argument("--action-timeout-seconds", type=float, default=120.0)
    step.add_argument("--execution-timeout-seconds", type=float, default=600.0)
    step.add_argument("--backend-apply-timeout-seconds", type=float, default=300.0)
    step.add_argument("--poll-interval-seconds", type=float, default=1.0)

    campaign = commands.add_parser(
        "run-campaign",
        help="Run an autonomous bounded single-qubit campaign",
    )
    campaign.add_argument("--session-id", required=True)
    campaign.add_argument("--qid", required=True)
    campaign.add_argument("--source-execution-id", required=True)
    campaign.add_argument("--plan", required=True, type=_campaign_plan)
    campaign.add_argument("--max-pre-dispatch-retries", type=int, default=1)
    campaign.add_argument("--max-node-executions", type=int)
    campaign.add_argument("--commit-on-success", action="store_true")
    campaign.add_argument("--idempotency-prefix")
    campaign.add_argument("--action-timeout-seconds", type=float, default=120.0)
    campaign.add_argument("--execution-timeout-seconds", type=float, default=600.0)
    campaign.add_argument("--backend-apply-timeout-seconds", type=float, default=300.0)
    campaign.add_argument("--poll-interval-seconds", type=float, default=1.0)

    return parser


def _outcome_payload(outcome: AgentStepOutcome) -> dict[str, Any]:
    return {
        "transition": outcome.transition.value,
        "reason": outcome.reason,
        "session_id": outcome.session_id,
        "action_id": outcome.action_id,
        "operation_id": outcome.operation_id,
        "execution_id": outcome.execution_id,
        "action": outcome.action.model_dump(mode="json") if outcome.action else None,
        "candidate": (outcome.candidate.model_dump(mode="json") if outcome.candidate else None),
        "commit": outcome.commit.model_dump(mode="json") if outcome.commit else None,
    }


def _campaign_outcome_payload(outcome: AgentCampaignOutcome) -> dict[str, Any]:
    return {
        "transition": outcome.transition.value,
        "reason": outcome.reason,
        "session_id": outcome.session_id,
        "qid": outcome.qid,
        "source_execution_id": outcome.source_execution_id,
        "completed_nodes": outcome.completed_nodes,
        "attempts": outcome.attempts,
        "carried_overrides": outcome.carried_overrides,
        "node_path": outcome.node_path,
        "campaign_commit": (
            outcome.campaign_commit.model_dump(mode="json") if outcome.campaign_commit else None
        ),
        "planner_decisions": [
            {
                "target_node_id": decision.target_node_id,
                "reason": decision.reason,
            }
            for decision in outcome.planner_decisions
        ],
        "outcomes": [_outcome_payload(step) for step in outcome.outcomes],
    }


def run(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run-step" and args.apply_backend and not args.commit_candidate:
        parser.error("--apply-backend requires --commit")
    client = (
        QDashClient.from_env()
        if args.from_env
        else QDashClient.from_profile(args.profile or "default")
    )
    try:
        if args.command == "start-session":
            session = client.create_agent_session(
                chip_id=args.chip_id,
                policy={
                    "qids": args.qids,
                    "allowed_tasks": args.tasks,
                    "allowed_overrides": args.allowed_overrides,
                    "quality_gates": args.quality_gates,
                    "allow_reconfigure": args.allow_reconfigure,
                    "max_actions": args.max_actions,
                },
                expires_in_seconds=args.expires_in_seconds,
                skill_name=args.skill_name,
                skill_version=args.skill_version,
                skill_hash=args.skill_hash,
                model_name=args.model_name,
            )
            print(json.dumps(session.model_dump(mode="json"), sort_keys=True))
            return 0

        if args.command == "run-campaign":
            campaign_runner = AgentCampaignRunner(
                client,
                action_timeout_seconds=args.action_timeout_seconds,
                execution_timeout_seconds=args.execution_timeout_seconds,
                backend_apply_timeout_seconds=args.backend_apply_timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
            campaign_outcome = campaign_runner.run_campaign(
                session_id=args.session_id,
                qid=args.qid,
                source_execution_id=args.source_execution_id,
                nodes=args.plan,
                max_pre_dispatch_retries=args.max_pre_dispatch_retries,
                max_node_executions=args.max_node_executions,
                commit_on_success=args.commit_on_success,
                idempotency_prefix=args.idempotency_prefix,
            )
            print(json.dumps(_campaign_outcome_payload(campaign_outcome), sort_keys=True))
            return 0 if campaign_outcome.transition.value == "pass" else 2

        runner = AgentCalibrationRunner(
            client,
            action_timeout_seconds=args.action_timeout_seconds,
            execution_timeout_seconds=args.execution_timeout_seconds,
            backend_apply_timeout_seconds=args.backend_apply_timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
        outcome = runner.run_step(
            session_id=args.session_id,
            task_name=args.task,
            qid=args.qid,
            source_execution_id=args.source_execution_id,
            candidate_parameter=args.candidate_parameter,
            parameter_overrides={
                str(key): float(value) for key, value in args.parameter_overrides.items()
            },
            diagnosis=args.diagnosis,
            reconfigure_before_task=args.reconfigure_before_task,
            commit_candidate=args.commit_candidate,
            apply_backend=args.apply_backend,
            push_to_github=args.push_to_github,
            action_idempotency_key=args.action_idempotency_key,
            commit_idempotency_key=args.commit_idempotency_key,
            backend_apply_idempotency_key=args.backend_apply_idempotency_key,
        )
        print(json.dumps(_outcome_payload(outcome), sort_keys=True))
        return 0 if outcome.transition.value == "pass" else 2
    finally:
        client.close()


def main() -> None:
    """Console-script entry point."""
    raise SystemExit(run())


if __name__ == "__main__":
    main()
