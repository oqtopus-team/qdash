# import requests
# from prefect import task


# @task
# def input_metrics(bluefors_server_url, channel_nr, start_time_str, stop_time_str):
#     payload = {
#         "channel_nr": channel_nr,
#         "start_time": start_time_str,
#         "stop_time": stop_time_str,
#         "fields": [
#             "timestamp",
#             "resistance",
#             "reactance",
#             "temperature",
#             "rez",
#             "imz",
#             "magnitude",
#             "angle",
#             "status_flags",
#         ],
#     }
#     headers = {"Content-Type": "application/json"}
#     response = requests.post(bluefors_server_url, headers=headers, json=payload)
#     metrics = response.json()
#     return metrics


# @task
# def get_latest_temperature(device_id, channel_nr):
#     from workflow.db.bluefors import get_latest_temperature

#     return get_latest_temperature(device_id, channel_nr)


# @task
# def output_metrics(metrics, device_id):
#     from workflow.db.bluefors import upsert_metrics

#     upsert_metrics(metrics, device_id)


# @task
# def check_and_alert(transformed_data, slack_webhook_url):
#     for record in transformed_data:
#         # TODO 各channelの閾値
#         if (
#             (record["channel_nr"] == 1 and record["temperature"] > 41)
#             or (record["channel_nr"] == 2 and record["temperature"] > 5)
#             or (record["channel_nr"] == 5 and record["temperature"] > 2)
#             or (record["channel_nr"] == 6 and record["temperature"] > 1)
#         ):
#             channel_nr = record["channel_nr"]
#             temperature = record["temperature"]

#             # TODO Slackにアラートを送信
#             message = (
#                 f"Warning: Temperature is high! channel={channel_nr} temperature={temperature}[K]"
#             )
#             payload = {"text": message}
#             response = requests.post(slack_webhook_url, json=payload)
#             if response.status_code == 200:
#                 print("Slack alert sent.")
#             else:
#                 print(f"Failed to send Slack alert. Status code: {response.status_code}")
