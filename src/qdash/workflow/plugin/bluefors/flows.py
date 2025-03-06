# from datetime import datetime, timedelta, timezone

# from prefect import flow, get_run_logger
# from qdash.workflow.plugin.bluefors.tasks import (
#     get_latest_temperature,
#     # output_metrics,
#     input_metrics,
# )


# @flow
# def bluefors_collector():
#     logger = get_run_logger()
#     # メトリクスを取得するためのパラメータ
#     channel_list = [1, 2, 5, 6]
#     device_id = "XLD"
#     stop_time = datetime.now(timezone.utc)
#     start_time = stop_time - timedelta(seconds=70)

#     start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
#     stop_time_str = stop_time.strftime("%Y-%m-%dT%H:%M:%SZ")
#     logger.info(f"start_time={start_time_str}, stop_time={stop_time_str}")
#     for channel_nr in channel_list:
#         try:
#             logger.info(f"Processing channel={channel_nr}")
#             import os

#             print(os.environ.get("BLUEFORS_HOST"))
#             api_url = f"http://{os.environ.get('BLUEFORS_HOST')}:5001/channel/historical-data"
#             metrics = input_metrics(
#                 api_url,
#                 channel_nr,
#                 start_time_str,
#                 stop_time_str,
#             )
#             from .tasks import output_metrics

#             output_metrics(metrics, device_id)
#             logger.info(f"Processing channel={channel_nr} completed")
#         except Exception as e:
#             print(f"Error occurred for channel={channel_nr}: {e}")


# @flow(flow_run_name="Fridge Alert")
# def fridge_alert():
#     for channel in [2, 6]:
#         check_and_update_fridge_status(channel, "XLD")


# def check_and_update_fridge_status(channel: int, id: str):
#     """This alert notifies the user when the temperature of the fridge is higher than the threshold, (e.g., 5.0K for channel 2 and 0.02K for channel 6).
#     Also, it notifies the user when the temperature is back to normal.
#     """
#     import os

#     from workflow.db.fridge_status import (
#         get_fridge_status,
#         insert_fridge_status,
#         update_fridge_status,
#     )
#     from workflow.utils.slack import SlackContents, Status

#     fridge_status = get_fridge_status(id)
#     if fridge_status is None:
#         fridge_status = insert_fridge_status(id)

#     channel_info = None
#     channel_name = ""
#     if channel == 2:
#         channel_info = fridge_status.ch2
#         channel_name = "4K-FLANGE"
#     elif channel == 6:
#         channel_info = fridge_status.ch6
#         channel_name = "MXC-FLANGE"

#     if channel_info is None:
#         return

#     prev_status = channel_info.status
#     logger = get_run_logger()
#     logger.info(f"Processing channel={channel} status={prev_status}")
#     threshold = channel_info.threshold
#     temp = get_latest_temperature(id, channel)
#     current_status = "normal"
#     if temp > threshold:
#         current_status = "abnormal"
#         logger.info(f"Temperature is high! channel={channel} temperature={temp}[K]")
#     if prev_status == "normal" and current_status == "abnormal":
#         logger.info(f"Temperature is high! channel={channel} temperature={temp}[K]")
#         update_fridge_status(id, channel, "abnormal")
#         contents = SlackContents(
#             status=Status.FAILED,
#             title=":rotating_light:ABNORMAL",
#             header="<!channel> Temperature is high!!",
#             msg=f"channel={channel}: {channel_name} temperature={temp}[K] > threshold={threshold}[K]",
#             notify=True,
#             ts="",
#             path="",
#             channel="#qiqb超伝導班",
#             token=os.environ.get("FRIDGE_ALERT_SLACK_BOT_TOKEN"),
#         )
#         contents.send_slack()
#     elif prev_status == "abnormal" and current_status == "normal":
#         logger.info(f"Temperature is back to normal. channel={channel} temperature={temp}[K]")
#         update_fridge_status(id, channel, "normal")
#         contents = SlackContents(
#             status=Status.SUCCESS,
#             title=":white_check_mark:NORMAL",
#             header="<!channel> Temperature is back to normal.",
#             msg=f"channel={channel}: {channel_name} temperature={temp}[K] < threshold={threshold}[K]",
#             notify=True,
#             ts="",
#             path="",
#             channel="#qiqb超伝導班",
#             token=os.environ.get("FRIDGE_ALERT_SLACK_BOT_TOKEN"),
#         )
#         contents.send_slack()


# if __name__ == "__main__":
#     bluefors_collector()
