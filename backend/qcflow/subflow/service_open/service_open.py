import requests
from prefect import flow
from pydantic import BaseModel
from qcflow.utils.slack import SlackContents, Status

restart_url = "http://localhost:5715/service"
url = "http://localhost:5715/service/status"


class CloudSetting(BaseModel):
    status: str
    mode: str
    qubit_num: int
    qubit_index: str


@flow(name="qpu-open", log_prints=True)
def qpu_open_flow():
    response = requests.get(url)
    settings = response.json()
    settings["status"] = "available"
    settings["mode"] = "qpu"
    response = requests.patch(url, json=settings)
    _ = requests.put(restart_url)
    contents = SlackContents(
        status=Status.SUCCESS,
        title="QPU Open",
        msg=f"{response.json()}",
        notify=True,
        ts="",
        path="",
    )
    contents.send_slack()


@flow(name="simulator-open", log_prints=True)
def simulator_open_flow():
    response = requests.get(url)
    settings = response.json()
    settings["status"] = "available"
    settings["mode"] = "simulator"
    response = requests.patch(url, json=settings)
    _ = requests.put(restart_url)
    contents = SlackContents(
        status=Status.SUCCESS,
        title="Simulator Open",
        msg=f"{response.json()}",
        notify=True,
        ts="",
        path="",
    )
    contents.send_slack()