from dataclasses import dataclass
from enum import Enum

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class Status(Enum):
    SUCCESS = 1
    RUNNING = 2
    RETRY = 3
    FAILED = 4


@dataclass
class SlackContents:
    status: Status
    title: str
    msg: str
    notify: bool
    ts: str
    path: str
    header: str = ""
    channel: str = "#slack-bot-test"

    def __init__(
        self,
        status: Status,
        title: str,
        msg: str,
        notify: bool,
        ts: str,
        path: str,
        header: str = "",
        channel: str = "#slack-bot-test",
        token: str = "",
    ):
        self.status = status
        self.title = title
        self.msg = msg
        self.notify = notify
        self.ts = ts
        self.path = path
        self.header = header
        self.channel = channel
        self.token = token

    def send_slack(self) -> str:
        if not self.notify:
            return ""
        # token = os.environ.get("SLACK_BOT_TOKEN")
        if self.token is None:
            return ""
        client = WebClient(token=self.token)
        if self.status == Status.SUCCESS:
            color = "good"
        elif self.status == Status.RUNNING:
            color = "#2E64FE"
        elif self.status == Status.RETRY:
            color = "warning"
        elif self.status == Status.FAILED:
            color = "danger"
        else:
            color = ""
        try:
            if self.ts != "":
                client.files_upload(
                    channels=self.channel,
                    file=self.path,
                    title=self.title,
                    thread_ts=self.ts,
                )
                return self.ts
            resp = client.chat_postMessage(
                channel=self.channel,
                text=self.header,
                attachments=[
                    {
                        "color": color,
                        "title": self.title,
                        "text": self.msg,
                    }
                ],
            )
            return str(resp["ts"])
        except SlackApiError as e:
            print(f"Got an error: {e.response['error']}")
            return ""
        except Exception as e:
            print(f"Got an error: {e}")
            raise e
