import os

import os
import pendulum
from prefect import flow, get_run_logger
from qdash.config import get_settings
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.initialize import initialize
from qdash.workflow.core.session.factory import create_session
from qdash.workflow.utils.slack import SlackContents, Status
from qdash.workflow.utiltask.create_directory import (
    create_directory_task,
)
from qdash.workflow.worker.flows.chip_report.generate_report import generate_chip_info_report
from qdash.workflow.worker.flows.push_props.create_props import (
    get_chip_properties,
    merge_properties,
)
from qdash.workflow.worker.flows.push_props.io import ChipPropertyYAMLHandler
from qdash.workflow.worker.tasks.pull_github import pull_github


@flow(name="chip-report", flow_run_name="Generate Chip Report")
def chip_report(username: str = "admin", source_path: str = "", slack_channel: str = "", slack_thread_ts: str = "") -> None:
    """Flow to generate and push chip report.

    Args:
    ----
        username: Username for the operation.
        source_path: Path to the source YAML file.
        slack_channel: Slack channel ID to send results to.
        slack_thread_ts: Slack thread timestamp to reply to.

    Returns:
    -------
        None

    """

    commit_id = "local" if os.getenv("CONFIG_REPO_URL") == "" else pull_github()
    initialize()
    date_str = pendulum.now(tz="Asia/Tokyo").date().strftime("%Y%m%d")
    chip_info_dir = f"/app/calib_data/{username}/{date_str}/chip_info"
    create_directory_task.submit(chip_info_dir).result()

    chip = ChipDocument.get_current_chip(username=username)
    logger = get_run_logger()
    logger.info(f"Current chip: {chip.chip_id}")
    source_path = f"/app/config/qubex/{chip.chip_id}/params/props.yaml"
    session = create_session(
        backend="qubex",
        config={
            "chip_id": chip.chip_id,
        },
    )
    props = get_chip_properties(chip, session=session, within_24hrs=False)
    handler = ChipPropertyYAMLHandler(source_path)
    base = handler.read()
    merged = merge_properties(base, props, chip_id=chip.chip_id)
    props_save_path = f"{chip_info_dir}/props.yaml"
    handler.write(merged, props_save_path)

    # 24時間以内のデータを抽出（マージせずに空のベースから作成）
    props_24h = get_chip_properties(chip, session=session, within_24hrs=True)
    from ruamel.yaml.comments import CommentedMap

    base_24h = CommentedMap()
    merged_24h = merge_properties(base_24h, props_24h, chip_id=chip.chip_id)
    props_save_path_24h = f"{chip_info_dir}/props_24h.yaml"
    handler_24h = ChipPropertyYAMLHandler(source_path)
    handler_24h.write(merged_24h, props_save_path_24h)
    generate_chip_info_report(chip_info_dir=chip_info_dir, chip_id=chip.chip_id)
    settings = get_settings()
    
    # Use provided slack channel/thread or fallback to settings
    target_channel = slack_channel if slack_channel else settings.slack_channel_id
    target_thread_ts = slack_thread_ts if slack_thread_ts else ""
    
    logger.info(f"Slack parameters - Channel: {target_channel}, Thread: {target_thread_ts}")
    logger.info(f"Received params - slack_channel: {slack_channel}, slack_thread_ts: {slack_thread_ts}")
    
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
    return merged
