import os
from typing import Any

import pendulum
from prefect import flow, get_run_logger
from qdash.config import get_settings
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.initialize import initialize
from qdash.workflow._internal.slack import SlackContents, Status
from qdash.workflow.engine.backend.factory import create_backend
from qdash.workflow.worker.flows.chip_report.generate_report import generate_chip_info_report
from qdash.workflow.worker.flows.push_props.create_props import (
    get_chip_properties,
    merge_properties,
)
from qdash.workflow.worker.flows.push_props.io import ChipPropertyYAMLHandler
from qdash.workflow.worker.tasks.filesystem import (
    create_directory_task,
)
from qdash.workflow.worker.tasks.pull_github import pull_github


def generate_data_availability_message(stats: dict[str, Any]) -> str:
    """Generate a message about data availability."""
    cutoff_hours = stats["cutoff_hours"]
    total_qubits = stats["total_qubits"]
    qubits_with_data = stats["qubits_with_recent_data"]
    total_couplings = stats["total_couplings"]
    couplings_with_data = stats["couplings_with_recent_data"]

    qubit_percentage = (qubits_with_data / total_qubits * 100) if total_qubits > 0 else 0
    coupling_percentage = (
        (couplings_with_data / total_couplings * 100) if total_couplings > 0 else 0
    )

    lines = []
    lines.append(f"**過去{cutoff_hours}時間の測定データ状況:**")
    lines.append("")

    if qubits_with_data == 0:
        lines.append(f"⚠️ **過去{cutoff_hours}時間以内に量子ビットの測定データがありません**")
        lines.append("- 全てのデータが古い可能性があります")
        lines.append("- 新しいキャリブレーションの実行を検討してください")
    else:
        lines.append(
            f"📊 **量子ビットデータ**: {qubits_with_data}/{total_qubits} ({qubit_percentage:.1f}%)"
        )
        if qubit_percentage < 50:
            lines.append("⚠️ 最近のデータが不足しています")
        elif qubit_percentage < 80:
            lines.append("⚡ 一部のデータが古い可能性があります")
        else:
            lines.append("✅ 十分な最新データがあります")

    if total_couplings > 0:
        lines.append(
            f"🔗 **カップリングデータ**: {couplings_with_data}/{total_couplings} ({coupling_percentage:.1f}%)"
        )

    if qubits_with_data < total_qubits:
        missing_count = total_qubits - qubits_with_data
        lines.append(f"🔄 {missing_count}個の量子ビットで最新データが不足")

    return "\n".join(lines)


@flow(name="chip-report", flow_run_name="Generate Chip Report")
def chip_report(
    username: str = "admin",
    source_path: str = "",
    slack_channel: str = "",
    slack_thread_ts: str = "",
    cutoff_hours: int = 24,
) -> None:
    """Flow to generate and push chip report.

    Args:
    ----
        username: Username for the operation.
        source_path: Path to the source YAML file.
        slack_channel: Slack channel ID to send results to.
        slack_thread_ts: Slack thread timestamp to reply to.
        cutoff_hours: Time window in hours for recent data filtering (default: 24).
        slack_thread_ts: Slack thread timestamp to reply to.

    Returns:
    -------
        None

    """

    _ = "local" if os.getenv("CONFIG_REPO_URL") == "" else pull_github()
    initialize()
    date_str = pendulum.now(tz="Asia/Tokyo").date().strftime("%Y%m%d")
    chip_info_dir = f"/app/calib_data/{username}/{date_str}/chip_info"
    create_directory_task.submit(chip_info_dir).result()

    chip = ChipDocument.get_current_chip(username=username)
    logger = get_run_logger()
    logger.info(f"Current chip: {chip.chip_id}")
    source_path = f"/app/config/qubex/{chip.chip_id}/params/props.yaml"
    backend = create_backend(
        backend="qubex",
        config={
            "chip_id": chip.chip_id,
        },
    )
    props, _ = get_chip_properties(chip, backend=backend, within_24hrs=False)
    handler = ChipPropertyYAMLHandler(source_path)
    base = handler.read()
    merged = merge_properties(base, props, chip_id=chip.chip_id)
    props_save_path = f"{chip_info_dir}/props.yaml"
    handler.write(merged, props_save_path)

    # 指定時間以内のデータを抽出（マージせずに空のベースから作成）
    props_recent, recent_stats = get_chip_properties(
        chip, backend=backend, within_24hrs=True, cutoff_hours=cutoff_hours
    )
    from ruamel.yaml.comments import CommentedMap

    base_recent = CommentedMap()
    merged_recent = merge_properties(base_recent, props_recent, chip_id=chip.chip_id)
    props_save_path_recent = f"{chip_info_dir}/props_{cutoff_hours}h.yaml"
    handler_recent = ChipPropertyYAMLHandler(source_path)
    handler_recent.write(merged_recent, props_save_path_recent)
    generate_chip_info_report(chip_info_dir=chip_info_dir, chip_id=chip.chip_id)
    settings = get_settings()

    # Use provided slack channel/thread or fallback to settings
    target_channel = slack_channel if slack_channel else settings.slack_channel_id
    target_thread_ts = slack_thread_ts if slack_thread_ts else ""

    logger.info(f"Slack parameters - Channel: {target_channel}, Thread: {target_thread_ts}")
    logger.info(
        f"Received params - slack_channel: {slack_channel}, slack_thread_ts: {slack_thread_ts}"
    )

    slack = SlackContents(
        status=Status.SUCCESS,
        title="🧪 For Experiment User",
        msg="Check the report.",
        ts=target_thread_ts,  # Use the provided thread ts (empty string creates new message)
        path="",
        header="For Experiment User",
        channel=target_channel,
        token=settings.slack_bot_token,
    )
    # Send the first message and get ts for subsequent messages
    sent_ts = slack.send_slack()

    # Use the thread_ts if provided, otherwise use the new message ts
    ts = target_thread_ts if target_thread_ts else sent_ts

    # Send data availability statistics if recent data was requested
    if (
        cutoff_hours != 24
        or recent_stats["qubits_with_recent_data"] < recent_stats["total_qubits"] * 0.8
    ):
        data_msg = generate_data_availability_message(recent_stats)
        slack_stats = SlackContents(
            status=Status.SUCCESS if recent_stats["qubits_with_recent_data"] > 0 else Status.FAILED,
            title=f"📊 Data Availability ({cutoff_hours}h)",
            msg=data_msg,
            ts=ts,
            path="",
            header=f"Recent Data Analysis ({cutoff_hours}h window)",
            channel=target_channel,
            token=settings.slack_bot_token,
        )
        slack_stats.send_slack()
    slack = SlackContents(
        status=Status.SUCCESS,
        title="props.yaml",
        msg="props.yaml updated successfully.",
        ts=ts,  # Use the thread ts (either from input or from first message)
        path=props_save_path,
        header=f"file: {props_save_path}",
        channel=target_channel,
        token=settings.slack_bot_token,
    )
    slack.send_slack()
    slack = SlackContents(
        status=Status.SUCCESS,
        title="chip_info_report.pdf",
        msg="chip_info_report.pdf updated successfully.",
        ts=ts,  # Use the thread ts (either from input or from first message)
        path=f"{chip_info_dir}/chip_info_report.pdf",
        header=f"file: {chip_info_dir}/chip_info_report.pdf",
        channel=target_channel,
        token=settings.slack_bot_token,
    )
    slack.send_slack()
    return None
