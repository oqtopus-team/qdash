#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import json
import os
import sys
from pathlib import Path
from typing import Any


SECRET_KEYS = {
    "api_token",
    "password",
    "cf_access_client_secret",
    "QDASH_API_TOKEN",
    "QDASH_PASSWORD",
    "QDASH_CF_ACCESS_CLIENT_SECRET",
}


def default_config_path() -> Path:
    xdg = os.getenv("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "qdash" / "config.ini"
    return Path("~/.config/qdash/config.ini").expanduser()


def add_qdash_checkout_to_path() -> None:
    candidates: list[Path] = []
    env_path = os.getenv("QDASH_REPO_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.append(Path("~/src/github.com/oqtopus-team/qdash").expanduser())
    candidates.append(Path(__file__).resolve().parents[3] / "qdash")

    for repo in candidates:
        src = repo / "src"
        if (src / "qdash" / "client").exists():
            sys.path.insert(0, str(src))
            return


def import_client_types() -> tuple[Any, Any]:
    add_qdash_checkout_to_path()
    try:
        from qdash.client import QDashClient, QDashConfig  # type: ignore
    except ModuleNotFoundError as exc:
        missing = exc.name or str(exc)
        if missing == "qdash":
            raise SystemExit(
                "Could not import qdash.client. Install qdash-client or set QDASH_REPO_PATH "
                "to a local oqtopus-team/qdash checkout."
            ) from exc
        raise SystemExit(
            f"Could not import qdash.client dependency '{missing}'. Install qdash-client, "
            "or run with: uv run --with qdash-client python "
            "skills/qdash/scripts/qdash_query.py ..."
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"Could not import qdash.client: {exc.__class__.__name__}: {exc}"
        ) from exc
    return QDashClient, QDashConfig


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    return value


def print_json(value: Any) -> None:
    print(json.dumps(to_jsonable(value), indent=2, sort_keys=True, ensure_ascii=False))


def parse_params(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise SystemExit("--params must be a JSON object")
    return parsed


def add_if_present(params: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        params[key] = value


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean value, got {value!r}")


def load_client(args: argparse.Namespace) -> Any:
    QDashClient, QDashConfig = import_client_types()
    if args.env:
        return QDashClient.from_env()
    if args.config:
        return QDashClient.from_profile(args.profile, path=args.config)
    return QDashClient.from_profile(args.profile)


def client_get(args: argparse.Namespace, path: str, params: dict[str, Any] | None = None) -> None:
    client = load_client(args)
    try:
        response = client._request("GET", path, params=params)  # noqa: SLF001
        print_json({"status_code": response.status_code, "data": response.data})
    finally:
        client.close()


def command_config_path(args: argparse.Namespace) -> None:
    path = Path(args.config).expanduser() if args.config else default_config_path()
    parser = configparser.ConfigParser()
    exists = path.exists()
    profiles: list[str] = []
    if exists:
        parser.read(path)
        profiles = parser.sections()
    print_json({"path": str(path), "exists": exists, "profiles": profiles})


def command_chips(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print_json(client.list_chips())
    finally:
        client.close()


def command_default_chip(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print_json(client.get_default_chip())
    finally:
        client.close()


def command_metrics_config(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print_json(client.get_metrics_config())
    finally:
        client.close()


def command_chip_metrics(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        chip_id = args.chip_id or client.get_default_chip_id()
        print_json(client.get_chip_metrics(chip_id))
    finally:
        client.close()


def command_chip_qubits(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        chip_id = args.chip_id or client.get_default_chip_id()
        print_json(
            client.list_chip_qubits(
                chip_id,
                qids=args.qid,
                offset=args.offset,
                limit=args.limit,
            )
        )
    finally:
        client.close()


def command_chip_qubit(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        chip_id = args.chip_id or client.get_default_chip_id()
        print_json(client.get_chip_qubit(chip_id, args.qid))
    finally:
        client.close()


def command_chip_couplings(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        chip_id = args.chip_id or client.get_default_chip_id()
        print_json(client.list_chip_couplings(chip_id, offset=args.offset, limit=args.limit))
    finally:
        client.close()


def command_chip_coupling(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        chip_id = args.chip_id or client.get_default_chip_id()
        print_json(client.get_chip_coupling(chip_id, args.coupling_id))
    finally:
        client.close()


def command_timeseries(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        chip_id = args.chip_id or client.get_default_chip_id()
        print_json(
            client.get_task_results_timeseries(
                chip_id=chip_id,
                parameter=args.parameter,
                tag=args.tag,
                qid=args.qid,
                start_at=args.start_at,
                end_at=args.end_at,
            )
        )
    finally:
        client.close()


def command_raw_get(args: argparse.Namespace) -> None:
    client_get(args, args.path, parse_params(args.params))


def command_task_results(args: argparse.Namespace) -> None:
    params: dict[str, Any] = {"skip": args.skip, "limit": args.limit}
    for key in (
        "status",
        "chip_id",
        "task_name",
        "qid",
        "execution_id",
        "username",
        "start_from",
        "start_to",
        "message_contains",
    ):
        add_if_present(params, key, getattr(args, key))
    client_get(args, "/task-results", params)


def command_qubit_latest(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        chip_id = args.chip_id or client.get_default_chip_id()
        response = client._request(  # noqa: SLF001
            "GET",
            "/task-results/qubits/latest",
            params={"chip_id": chip_id, "task": args.task},
        )
        print_json({"status_code": response.status_code, "data": response.data})
    finally:
        client.close()


def command_qubit_history(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        chip_id = args.chip_id or client.get_default_chip_id()
        response = client._request(  # noqa: SLF001
            "GET",
            f"/task-results/qubits/{args.qid}/history",
            params={"chip_id": chip_id, "task": args.task, "date": args.date},
        )
        print_json({"status_code": response.status_code, "data": response.data})
    finally:
        client.close()


def command_coupling_latest(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        chip_id = args.chip_id or client.get_default_chip_id()
        response = client._request(  # noqa: SLF001
            "GET",
            "/task-results/couplings/latest",
            params={"chip_id": chip_id, "task": args.task},
        )
        print_json({"status_code": response.status_code, "data": response.data})
    finally:
        client.close()


def command_coupling_history(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        chip_id = args.chip_id or client.get_default_chip_id()
        response = client._request(  # noqa: SLF001
            "GET",
            f"/task-results/couplings/{args.coupling_id}/history",
            params={"chip_id": chip_id, "task": args.task, "date": args.date},
        )
        print_json({"status_code": response.status_code, "data": response.data})
    finally:
        client.close()


def command_projects(args: argparse.Namespace) -> None:
    client_get(args, "/projects")


def command_project(args: argparse.Namespace) -> None:
    client_get(args, f"/projects/{args.project_id}")


def command_files_tree(args: argparse.Namespace) -> None:
    client_get(args, "/files/tree")


def command_file_content(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print_json(client.get_file_content(args.path))
    finally:
        client.close()


def command_git_status(args: argparse.Namespace) -> None:
    client_get(args, "/files/git/status")


def command_task_result(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print_json(client.get_task_result(args.task_id))
    finally:
        client.close()


def command_task_note(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print_json(client.get_task_note(args.task_id))
    finally:
        client.close()


def command_task_result_issues(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print_json(client.list_task_result_issues(args.task_id))
    finally:
        client.close()


def command_task_knowledge(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        if args.task_name:
            print_json(client.get_task_knowledge(args.task_name))
        else:
            print_json(client.list_task_knowledge())
    finally:
        client.close()


def command_task_knowledge_markdown(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print(client.get_task_knowledge_markdown(args.task_name))
    finally:
        client.close()


def command_issues(args: argparse.Namespace) -> None:
    params: dict[str, Any] = {"skip": args.skip, "limit": args.limit}
    add_if_present(params, "task_id", args.task_id)
    add_if_present(params, "is_closed", args.is_closed)
    client_get(args, "/issues", params)


def command_issue_knowledge(args: argparse.Namespace) -> None:
    params: dict[str, Any] = {"skip": args.skip, "limit": args.limit}
    add_if_present(params, "status", args.status)
    add_if_present(params, "task_name", args.task_name)
    client_get(args, "/issue-knowledge", params)


def command_flows(args: argparse.Namespace) -> None:
    client_get(args, "/flows")


def command_flow(args: argparse.Namespace) -> None:
    client_get(args, f"/flows/{args.name}")


def command_flow_templates(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print_json(client.list_flow_templates())
    finally:
        client.close()


def command_flow_template(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print_json(client.get_flow_template(args.template_id))
    finally:
        client.close()


def command_flow_helper_files(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print_json(client.list_flow_helper_files())
    finally:
        client.close()


def command_flow_helper_file(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print(client.get_flow_helper_file(args.filename))
    finally:
        client.close()


def command_executions(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        chip_id = args.chip_id or client.get_default_chip_id()
        response = client._request(  # noqa: SLF001
            "GET",
            "/executions",
            params={"chip_id": chip_id, "skip": args.skip, "limit": args.limit},
        )
        print_json({"status_code": response.status_code, "data": response.data})
    finally:
        client.close()


def command_ai_reviews(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print_json(
            client.list_task_result_ai_reviews(
                chip_id=args.chip_id,
                task_name=args.task_name,
                status=args.status,
                decision=args.decision,
                latest_only=args.latest_only,
                skip=args.skip,
                limit=args.limit,
            )
        )
    finally:
        client.close()


def command_ai_review_runs(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print_json(
            client.list_task_result_ai_review_runs(
                chip_id=args.chip_id,
                task_name=args.task_name,
                skip=args.skip,
                limit=args.limit,
            )
        )
    finally:
        client.close()


def command_ai_review_run(args: argparse.Namespace) -> None:
    client = load_client(args)
    try:
        print_json(client.get_task_result_ai_review_run(args.review_run_id))
    finally:
        client.close()


def command_provenance_stats(args: argparse.Namespace) -> None:
    client_get(args, "/provenance/stats")


def command_provenance_history(args: argparse.Namespace) -> None:
    params = {
        "parameter_name": args.parameter_name,
        "qid": args.qid,
        "limit": args.limit,
    }
    client_get(args, "/provenance/history", params)


def command_provenance_changes(args: argparse.Namespace) -> None:
    params: dict[str, Any] = {"limit": args.limit, "within_hours": args.within_hours}
    if args.parameter_name:
        params["parameter_names"] = args.parameter_name
    client_get(args, "/provenance/changes", params)


def command_provenance_entity(args: argparse.Namespace) -> None:
    client_get(args, f"/provenance/entities/{args.entity_id}")


def command_provenance_lineage(args: argparse.Namespace) -> None:
    client_get(args, f"/provenance/lineage/{args.entity_id}")


def command_provenance_impact(args: argparse.Namespace) -> None:
    client_get(args, f"/provenance/impact/{args.entity_id}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read QDash data through qdash-client profiles.")
    parser.add_argument("--profile", default="default", help="qdash-client profile name")
    parser.add_argument("--config", help="Path to qdash config.ini")
    parser.add_argument("--env", action="store_true", help="Load QDASH_* environment variables")

    sub = parser.add_subparsers(dest="command", required=True)

    config_path = sub.add_parser("config-path", help="Show config path and profile names only")
    config_path.set_defaults(func=command_config_path)

    chips = sub.add_parser("chips", help="List chips")
    chips.set_defaults(func=command_chips)

    default_chip = sub.add_parser("default-chip", help="Show the default chip")
    default_chip.set_defaults(func=command_default_chip)

    metrics_config = sub.add_parser("metrics-config", help="Show metrics configuration")
    metrics_config.set_defaults(func=command_metrics_config)

    chip_metrics = sub.add_parser("chip-metrics", help="Show dashboard metrics for a chip")
    chip_metrics.add_argument("--chip-id", help="Defaults to get_default_chip_id()")
    chip_metrics.set_defaults(func=command_chip_metrics)

    chip_qubits = sub.add_parser("chip-qubits", help="List qubits for a chip")
    chip_qubits.add_argument("--chip-id", help="Defaults to get_default_chip_id()")
    chip_qubits.add_argument("--qid", action="append", help="Filter by qubit ID; repeatable")
    chip_qubits.add_argument("--offset", type=int, default=0)
    chip_qubits.add_argument("--limit", type=int, default=50)
    chip_qubits.set_defaults(func=command_chip_qubits)

    chip_qubit = sub.add_parser("chip-qubit", help="Show one qubit for a chip")
    chip_qubit.add_argument("--chip-id", help="Defaults to get_default_chip_id()")
    chip_qubit.add_argument("--qid", required=True)
    chip_qubit.set_defaults(func=command_chip_qubit)

    chip_couplings = sub.add_parser("chip-couplings", help="List couplings for a chip")
    chip_couplings.add_argument("--chip-id", help="Defaults to get_default_chip_id()")
    chip_couplings.add_argument("--offset", type=int, default=0)
    chip_couplings.add_argument("--limit", type=int, default=100)
    chip_couplings.set_defaults(func=command_chip_couplings)

    chip_coupling = sub.add_parser("chip-coupling", help="Show one coupling for a chip")
    chip_coupling.add_argument("--chip-id", help="Defaults to get_default_chip_id()")
    chip_coupling.add_argument("--coupling-id", required=True)
    chip_coupling.set_defaults(func=command_chip_coupling)

    timeseries = sub.add_parser("timeseries", help="Show task result time-series data")
    timeseries.add_argument("--chip-id", help="Defaults to get_default_chip_id()")
    timeseries.add_argument("--parameter", required=True)
    timeseries.add_argument("--tag")
    timeseries.add_argument("--qid")
    timeseries.add_argument("--start-at", required=True)
    timeseries.add_argument("--end-at", required=True)
    timeseries.set_defaults(func=command_timeseries)

    raw_get = sub.add_parser("raw-get", help="Run a read-only GET request against an API path")
    raw_get.add_argument("--path", required=True)
    raw_get.add_argument("--params", help="JSON object of query parameters")
    raw_get.set_defaults(func=command_raw_get)

    task_results = sub.add_parser("task-results", help="List task results with common filters")
    task_results.add_argument("--status")
    task_results.add_argument("--chip-id")
    task_results.add_argument("--task-name")
    task_results.add_argument("--qid")
    task_results.add_argument("--execution-id")
    task_results.add_argument("--username")
    task_results.add_argument("--start-from", help="Inclusive lower bound, ISO datetime")
    task_results.add_argument("--start-to", help="Inclusive upper bound, ISO datetime")
    task_results.add_argument("--message-contains")
    task_results.add_argument("--skip", type=int, default=0)
    task_results.add_argument("--limit", type=int, default=50)
    task_results.set_defaults(func=command_task_results)

    qubit_latest = sub.add_parser("qubit-latest", help="Latest task result values by qubit")
    qubit_latest.add_argument("--chip-id", help="Defaults to get_default_chip_id()")
    qubit_latest.add_argument("--task", required=True)
    qubit_latest.set_defaults(func=command_qubit_latest)

    qubit_history = sub.add_parser("qubit-history", help="Historical task result values for a qubit")
    qubit_history.add_argument("--chip-id", help="Defaults to get_default_chip_id()")
    qubit_history.add_argument("--qid", required=True)
    qubit_history.add_argument("--task", required=True)
    qubit_history.add_argument("--date", required=True, help="Date in YYYYMMDD format")
    qubit_history.set_defaults(func=command_qubit_history)

    coupling_latest = sub.add_parser("coupling-latest", help="Latest task result values by coupling")
    coupling_latest.add_argument("--chip-id", help="Defaults to get_default_chip_id()")
    coupling_latest.add_argument("--task", required=True)
    coupling_latest.set_defaults(func=command_coupling_latest)

    coupling_history = sub.add_parser(
        "coupling-history", help="Historical task result values for a coupling"
    )
    coupling_history.add_argument("--chip-id", help="Defaults to get_default_chip_id()")
    coupling_history.add_argument("--coupling-id", required=True)
    coupling_history.add_argument("--task", required=True)
    coupling_history.add_argument("--date", required=True, help="Date in YYYYMMDD format")
    coupling_history.set_defaults(func=command_coupling_history)

    projects = sub.add_parser("projects", help="List projects visible to the profile")
    projects.set_defaults(func=command_projects)

    project = sub.add_parser("project", help="Show one project")
    project.add_argument("--project-id", required=True)
    project.set_defaults(func=command_project)

    files_tree = sub.add_parser("files-tree", help="Show project file tree")
    files_tree.set_defaults(func=command_files_tree)

    file_content = sub.add_parser("file-content", help="Show one project file's content")
    file_content.add_argument("--path", required=True)
    file_content.set_defaults(func=command_file_content)

    git_status = sub.add_parser("git-status", help="Show project git status")
    git_status.set_defaults(func=command_git_status)

    task_result = sub.add_parser("task-result", help="Show one task result by task ID")
    task_result.add_argument("--task-id", required=True)
    task_result.set_defaults(func=command_task_result)

    task_note = sub.add_parser("task-note", help="Show one task result note")
    task_note.add_argument("--task-id", required=True)
    task_note.set_defaults(func=command_task_note)

    task_result_issues = sub.add_parser(
        "task-result-issues", help="List issues attached to a task result"
    )
    task_result_issues.add_argument("--task-id", required=True)
    task_result_issues.set_defaults(func=command_task_result_issues)

    task_knowledge = sub.add_parser(
        "task-knowledge", help="List task knowledge, or show one entry with --task-name"
    )
    task_knowledge.add_argument("--task-name")
    task_knowledge.set_defaults(func=command_task_knowledge)

    task_knowledge_markdown = sub.add_parser(
        "task-knowledge-markdown", help="Show one task knowledge entry as markdown"
    )
    task_knowledge_markdown.add_argument("--task-name", required=True)
    task_knowledge_markdown.set_defaults(func=command_task_knowledge_markdown)

    issues = sub.add_parser("issues", help="List issues")
    issues.add_argument("--skip", type=int, default=0)
    issues.add_argument("--limit", type=int, default=50)
    issues.add_argument("--task-id")
    issues.add_argument("--is-closed", type=parse_bool)
    issues.set_defaults(func=command_issues)

    issue_knowledge = sub.add_parser("issue-knowledge", help="List issue knowledge entries")
    issue_knowledge.add_argument("--skip", type=int, default=0)
    issue_knowledge.add_argument("--limit", type=int, default=50)
    issue_knowledge.add_argument("--status", choices=["draft", "approved", "rejected"])
    issue_knowledge.add_argument("--task-name")
    issue_knowledge.set_defaults(func=command_issue_knowledge)

    flows = sub.add_parser("flows", help="List flows")
    flows.set_defaults(func=command_flows)

    flow = sub.add_parser("flow", help="Show one flow definition")
    flow.add_argument("--name", required=True)
    flow.set_defaults(func=command_flow)

    flow_templates = sub.add_parser("flow-templates", help="List flow templates")
    flow_templates.set_defaults(func=command_flow_templates)

    flow_template = sub.add_parser("flow-template", help="Show one flow template with code")
    flow_template.add_argument("--template-id", required=True)
    flow_template.set_defaults(func=command_flow_template)

    flow_helper_files = sub.add_parser("flow-helper-files", help="List flow helper files")
    flow_helper_files.set_defaults(func=command_flow_helper_files)

    flow_helper_file = sub.add_parser("flow-helper-file", help="Show one flow helper file")
    flow_helper_file.add_argument("--filename", required=True)
    flow_helper_file.set_defaults(func=command_flow_helper_file)

    executions = sub.add_parser("executions", help="List executions for a chip")
    executions.add_argument("--chip-id", help="Defaults to get_default_chip_id()")
    executions.add_argument("--skip", type=int, default=0)
    executions.add_argument("--limit", type=int, default=20)
    executions.set_defaults(func=command_executions)

    ai_reviews = sub.add_parser("ai-reviews", help="List task result AI reviews")
    ai_reviews.add_argument("--chip-id")
    ai_reviews.add_argument("--task-name")
    ai_reviews.add_argument("--status")
    ai_reviews.add_argument("--decision")
    ai_reviews.add_argument("--latest-only", action="store_true")
    ai_reviews.add_argument("--skip", type=int, default=0)
    ai_reviews.add_argument("--limit", type=int, default=50)
    ai_reviews.set_defaults(func=command_ai_reviews)

    ai_review_runs = sub.add_parser("ai-review-runs", help="List AI review runs")
    ai_review_runs.add_argument("--chip-id")
    ai_review_runs.add_argument("--task-name")
    ai_review_runs.add_argument("--skip", type=int, default=0)
    ai_review_runs.add_argument("--limit", type=int, default=50)
    ai_review_runs.set_defaults(func=command_ai_review_runs)

    ai_review_run = sub.add_parser("ai-review-run", help="Show one AI review run")
    ai_review_run.add_argument("--review-run-id", required=True)
    ai_review_run.set_defaults(func=command_ai_review_run)

    provenance_stats = sub.add_parser("provenance-stats", help="Show provenance statistics")
    provenance_stats.set_defaults(func=command_provenance_stats)

    provenance_history = sub.add_parser(
        "provenance-history", help="Show provenance history for a parameter and entity"
    )
    provenance_history.add_argument("--parameter-name", required=True)
    provenance_history.add_argument("--qid", required=True)
    provenance_history.add_argument("--limit", type=int, default=50)
    provenance_history.set_defaults(func=command_provenance_history)

    provenance_changes = sub.add_parser("provenance-changes", help="Show recent provenance changes")
    provenance_changes.add_argument("--limit", type=int, default=20)
    provenance_changes.add_argument("--within-hours", type=int, default=24)
    provenance_changes.add_argument(
        "--parameter-name",
        action="append",
        help="Filter by parameter name; repeat for multiple values",
    )
    provenance_changes.set_defaults(func=command_provenance_changes)

    provenance_entity = sub.add_parser("provenance-entity", help="Show one provenance entity")
    provenance_entity.add_argument("--entity-id", required=True)
    provenance_entity.set_defaults(func=command_provenance_entity)

    provenance_lineage = sub.add_parser("provenance-lineage", help="Show lineage for an entity")
    provenance_lineage.add_argument("--entity-id", required=True)
    provenance_lineage.set_defaults(func=command_provenance_lineage)

    provenance_impact = sub.add_parser("provenance-impact", help="Show impact for an entity")
    provenance_impact.add_argument("--entity-id", required=True)
    provenance_impact.set_defaults(func=command_provenance_impact)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:  # noqa: BLE001
        print_json({"error": exc.__class__.__name__, "message": str(exc)})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
