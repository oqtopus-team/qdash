from pathlib import Path

from prefect import flow
from prefect.logging import get_run_logger
from qdash.config import get_settings
from qdash.workflow.utils.slack import SlackContents, Status
from qdash.workflow.utiltask.create_directory import (
    create_directory_task,
)
from qdash.workflow.worker.device_gateway_integration.task import (
    DeviceTopologyRequest,
    generate_device_topology_request,
    generate_topology_plot,
    post_device_topology,
)


@flow(name="device-gateway-integration-flow")
def device_gateway_integration_flow(
    request: DeviceTopologyRequest, username: str = "admin"
) -> None:
    """Flow to integrate the device gateway with the system."""
    # Placeholder for actual implementation
    logging = get_run_logger()
    settings = get_settings()
    logging.info("Device Gateway Integration Flow started.")
    device_info_dir = f"/app/calib_data/{username}/device_info"
    create_directory_task.submit(device_info_dir).result()
    save_path = Path(device_info_dir)
    request = generate_device_topology_request(request, save_path)
    topology_data = post_device_topology(request, save_path)
    generate_topology_plot.submit(topology_data, save_path).result()
    request_file = save_path / "device_topology_request.json"
    device_topology_file = save_path / "device_topology.json"
    topology_figure_file = save_path / "device_topology.png"
    slack = SlackContents(
        status=Status.SUCCESS,
        title="🧑‍💻 For Cloud Operator",
        msg="Check the device topology request and response files.",
        ts="",
        path="",
        header="For Cloud Operator",
        channel=settings.slack_channel_id,
        token=settings.slack_bot_token,
    )
    ts = slack.send_slack()
    slack = SlackContents(
        status=Status.SUCCESS,
        title="device_topology_request.json",
        msg="Use this request to get the device topology.",
        ts=ts,
        path=str(request_file),
        header="For Cloud Operator",
        channel=settings.slack_channel_id,
        token=settings.slack_bot_token,
    )
    slack.send_slack()
    slack = SlackContents(
        status=Status.SUCCESS,
        title="device_topology.json",
        msg="This topology is reccommended for the Cloud Service.",
        ts=ts,
        path=str(device_topology_file),
        header="For Cloud Operator",
        channel=settings.slack_channel_id,
        token=settings.slack_bot_token,
    )
    slack.send_slack()
    slack = SlackContents(
        status=Status.SUCCESS,
        title="device_topology.png",
        msg="This topology is reccommended for the Cloud Service.",
        ts=ts,
        path=str(topology_figure_file),
        header="For Cloud Operator",
        channel=settings.slack_channel_id,
        token=settings.slack_bot_token,
    )
    slack.send_slack()
    logging.info("Device Gateway Integration Flow completed successfully.")
