# import requests
# from prefect import flow
# from pydantic import BaseModel
# from qdash.workflow.utils.slack import SlackContents, Status

# from qdash.api.config import get_settings
# settings = get_settings()
# restart_url = f"http://localhost:{settings.api_port}/service"
# url = f"http://localhost:{settings.api_port}/service/status"


# class CloudSetting(BaseModel):
#     status: str
#     mode: str
#     qubit_num: int
#     qubit_index: str


# @flow(name="qpu-close", log_prints=True)
# def qpu_close_flow():
#     response = requests.get(url)
#     settings = response.json()
#     settings["status"] = "unavailable"
#     settings["mode"] = "qpu"
#     response = requests.patch(url, json=settings)
#     _ = requests.put(restart_url)
#     contents = SlackContents(
#         status=Status.SUCCESS,
#         title="QPU Closing",
#         msg=f"{response.json()}",
#         notify=True,
#         ts="",
#         path="",
#     )
#     contents.send_slack()


# @flow(name="simulator-close", log_prints=True)
# def simulator_close_flow():
#     response = requests.get(url)
#     settings = response.json()
#     settings["status"] = "unavailable"
#     settings["mode"] = "simulator"
#     response = requests.patch(url, json=settings)
#     _ = requests.put(restart_url)
#     contents = SlackContents(
#         status=Status.SUCCESS,
#         title="Simulator Closing",
#         msg=f"{response.json()}",
#         notify=True,
#         ts="",
#         path="",
#     )
#     contents.send_slack()
