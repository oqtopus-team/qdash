"""Command-line entry point for user-operated QDash calibration agents."""

from __future__ import annotations

import argparse
import json
from typing import Any

from qdash.client.services.agent_runner import AgentCalibrationRunner, AgentStepOutcome
from qdash.client.services.client import QDashClient as QDashClient  # noqa: PLC0414


def _json_object(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("value must be a JSON object")
    return parsed


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
    step.add_argument("--parameter-overrides", type=_json_object, default={})
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
        "--no-github-push",
        action="store_false",
        dest="push_to_github",
        help="Skip versioning changed backend files in GitHub",
    )
    step.add_argument("--action-idempotency-key")
    step.add_argument("--commit-idempotency-key")
    step.add_argument("--backend-apply-idempotency-key")
    step.add_argument("--action-timeout-seconds", type=float, default=120.0)
    step.add_argument("--execution-timeout-seconds", type=float, default=600.0)
    step.add_argument("--backend-apply-timeout-seconds", type=float, default=300.0)
    step.add_argument("--poll-interval-seconds", type=float, default=1.0)

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
