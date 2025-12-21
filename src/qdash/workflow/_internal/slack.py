import logging
import os
from dataclasses import dataclass
from enum import Enum

from qdash.config import get_settings
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Status(Enum):
    """Status enum class."""

    SUCCESS = 1
    RUNNING = 2
    RETRY = 3
    FAILED = 4


@dataclass
class SlackContents:
    """Slack message class."""

    status: Status
    title: str
    msg: str
    ts: str
    path: str
    header: str = ""
    channel: str = ""  # Channel ID
    token: str = ""
    broadcast: bool = False  # Whether to also post thread replies to the channel

    def __init__(
        self,
        status: Status,
        title: str,
        msg: str,
        ts: str,
        path: str,
        header: str = "",
        channel: str = "",  # Channel ID
        token: str = "",
        broadcast: bool = False,  # Whether to also post thread replies to the channel
    ) -> None:
        """Initialize SlackContents."""
        self.status = status
        self.title = title
        self.msg = msg
        self.ts = ts
        self.path = path
        self.header = header
        self.channel = channel
        self.token = token
        self.broadcast = broadcast

    def update_contents(
        self,
        status: Status,
        title: str,
        msg: str,
        ts: str,
        path: str = "",
        broadcast: bool = False,
    ) -> None:
        """Update SlackContents.

        Args:
        ----
            status: Message status
            title: Message title
            msg: Message content
            ts: Thread timestamp (empty string for new message, parent ts for thread reply)
            path: File path for attachment (optional)
            broadcast: Whether to also post the reply to the channel (optional)

        """
        self.status = status
        self.title = title
        self.msg = msg
        self.ts = ts
        self.path = path
        self.broadcast = broadcast

    def _get_attachment(self) -> list[dict[str, str]]:
        """Get message attachment with color based on status."""
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

        return [
            {
                "color": color,
                "title": self.title,
                "text": self.msg,
            }
        ]

    def send_slack(self) -> str:
        """Send message to Slack.

        Returns
        -------
            str: Message timestamp (ts) that can be used for threading or updating

        """
        if self.token is None:
            return ""

        client = WebClient(token=self.token)
        attachments = self._get_attachment()

        try:
            # Case 1: Post new message or thread reply
            if not self.path:
                resp = client.chat_postMessage(
                    channel=self.channel,
                    text=self.header,
                    thread_ts=self.ts if self.ts != "" else None,
                    reply_broadcast=self.broadcast
                    if self.ts != ""
                    else False,  # Only valid for thread replies
                    attachments=attachments,
                )
                return str(resp["ts"])

            # Case 2: File upload with message
            # Check if file exists
            if not os.path.exists(self.path):
                logger.error(f"File not found: {self.path}")
                return ""

            logger.info(f"Uploading file: {self.path}")
            # First post a message
            resp = client.chat_postMessage(
                channel=self.channel,
                text=self.header,
                thread_ts=self.ts if self.ts != "" else None,
                reply_broadcast=self.broadcast
                if self.ts != ""
                else False,  # Only valid for thread replies
                attachments=attachments,
            )
            message_ts = str(resp["ts"])

            # Then upload the file in the thread
            try:
                # Upload file
                client.files_upload_v2(
                    channel=self.channel,
                    file=self.path,
                    title=self.title,
                    thread_ts=self.ts,
                )
                logger.info("File upload successful")
            except Exception as e:
                logger.error(f"File upload failed: {e}")
                # Return message ts even if file upload fails
            return message_ts

        except SlackApiError as e:
            logger.info(f"Got an error: {e.response['error']}")
            return ""
        except Exception as e:
            logger.info(f"Got an error: {e}")
            raise RuntimeError(f"Got an error: {e}") from e


if __name__ == "__main__":
    settings = get_settings()

    # 1. Post a new message
    slack = SlackContents(
        status=Status.RUNNING,
        title="Calibration Started",
        msg="Starting qubit calibration...",
        ts="",  # Empty ts for new message
        path="",
        header="Calibration Process",
        channel=settings.slack_channel_id,
        token=settings.slack_bot_token,
    )
    parent_ts = slack.send_slack()
    print(f"Parent message ts: {parent_ts}")

    # 2. Post progress message in thread
    slack.update_contents(
        status=Status.RUNNING,
        title="Step 1",
        msg="Performing frequency calibration...",
        ts=parent_ts,  # Use parent ts to post in thread
        broadcast=False,  # Don't broadcast to channel
    )
    slack.send_slack()

    # 3. Attach file in thread
    slack.update_contents(
        status=Status.SUCCESS,
        title="Calibration Result",
        msg="Frequency calibration completed",
        ts=parent_ts,  # Same thread
        path="",  # Result file
        broadcast=False,  # Don't broadcast to channel
    )
    slack.send_slack()

    # 4. Post completion message in thread (also broadcast to channel)
    slack.update_contents(
        status=Status.SUCCESS,
        title="Calibration Completed",
        msg="All calibration steps completed successfully",
        ts=parent_ts,  # Same thread
        path="",
        broadcast=True,  # Also broadcast to channel
    )
    slack.send_slack()
