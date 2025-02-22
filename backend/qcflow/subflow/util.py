import json
import os
import re
from pathlib import Path

from mermaid import Config, Graph, Mermaid
from prefect import get_run_logger
from prefect import task as prefect_task


def convert_qid(qid: str) -> str:
    """Convert QXX to XX. e.g."Q0" -> "0" "Q01" -> "1" """
    if re.fullmatch(r"Q\d+", qid):
        qid = qid[1:]
        return qid
    else:
        raise ValueError("Invalid qid format.")


def convert_label(qid: str) -> str:
    """Convert QXX to QXX. e.g. "0" -> "Q0" """
    if re.fullmatch(r"\d+", qid):
        qid = "Q" + qid
        return qid
    else:
        raise ValueError("Invalid qid format.")


def extract_tasks(data):
    tasks = []
    if "task_result" in data and "global_tasks" in data["task_result"]:
        for t in data["task_result"]["global_tasks"]:
            t["qid"] = "global"
            tasks.append(t)
    if "task_result" in data and "qubit_tasks" in data["task_result"]:
        for qid, task_list in data["task_result"]["qubit_tasks"].items():
            for task in task_list:
                task["qid"] = qid
                tasks.append(task)
    if "task_result" in data and "coupling_tasks" in data["task_result"]:
        for key, task_list in data["task_result"]["coupling_tasks"].items():
            for task in task_list:
                task["qid"] = "coupling"
                tasks.append(task)
    return tasks


def generate_mermaid_by_qid(tasks):
    """Generate a Mermaid diagram from the tasks grouped by qid."""
    groups = {}
    task_group = {}
    for task in tasks:
        qid = task.get("qid", "global")
        groups.setdefault(qid, []).append(task)
        tid = task.get("task_id")
        if tid:
            task_group[tid] = qid

    lines = []
    lines.append("flowchart TD")
    for qid, group_tasks in groups.items():
        if qid == "global":
            lines.append("subgraph Global Tasks")
        elif qid == "coupling":
            lines.append("subgraph Coupling Tasks")
        else:
            lines.append(f'subgraph "QID {qid}"')
        for task in group_tasks:
            tid = task.get("task_id")
            name = task.get("name", "")
            node_id = tid.replace("-", "_") if tid else ""
            lines.append(f'    {node_id}["{name}"]')
        for task in group_tasks:
            tid = task.get("task_id")
            upstream = task.get("upstream_id", "")
            if upstream and (task_group.get(upstream) == qid):
                src_id = upstream.replace("-", "_")
                dst_id = tid.replace("-", "_")
                lines.append(f"    {src_id} --> {dst_id}")
        lines.append("end")
        lines.append("")
    return "\n".join(lines)


@prefect_task
def generate_dag(file_path: str) -> None:
    """Generate a DAG from the input file and save it as a PNG file.

    Args:
    ----
        file_path: The path to the input file.

    """
    with Path(file_path).open() as f:
        data = json.load(f)
    tasks = extract_tasks(data)
    mermaid_diagram = generate_mermaid_by_qid(tasks)
    config = Config(theme="dark")
    graph = Graph(title="Combined Tasks", script=mermaid_diagram, config=config)
    m = Mermaid(graph)

    base_name = Path(file_path).stem
    output_dir = Path(file_path).parent
    output_path = output_dir / f"{base_name}.png"

    m.to_png(output_path)


@prefect_task
def update_active_output_parameters() -> None:
    """Update the active output parameters in the input file.

    Args:
    ----
        file_path: The path to the input file.

    """
    from qcflow.subflow.protocols.base import BaseTask

    logger = get_run_logger()
    all_outputs = {name: cls.output_parameters for name, cls in BaseTask.registry.items()}
    unique_elements = list({param for params in all_outputs.values() for param in params})
    logger.info(f"Active output parameters: {unique_elements}")
    with Path("active_output_parameters.json").open("w") as f:
        json.dump(all_outputs, f)
    with Path("unique_output_parameters.json").open("w") as f:
        json.dump(unique_elements, f)

    all_descriptions = {name: cls.__doc__ for name, cls in BaseTask.registry.items()}
    with Path("task_descriptions.json").open("w") as f:
        json.dump(all_descriptions, f)
    logger.info(f"Task descriptions: {all_descriptions}")
