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
    channel: str = ""  # デフォルトのチャンネルID
    token: str = ""
    broadcast: bool = False  # スレッド内の返信をチャンネルにも表示するかどうか

    def __init__(
        self,
        status: Status,
        title: str,
        msg: str,
        ts: str,
        path: str,
        header: str = "",
        channel: str = "",  # デフォルトのチャンネルID
        token: str = "",
        broadcast: bool = False,  # スレッド内の返信をチャンネルにも表示するかどうか
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
                    else False,  # スレッド内の返信時のみ有効
                    attachments=attachments,
                )
                return str(resp["ts"])

            # Case 2: File upload with message
            # ファイルの存在確認
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
                else False,  # スレッド内の返信時のみ有効
                attachments=attachments,
            )
            message_ts = str(resp["ts"])

            # Then upload the file in the thread
            try:
                # ファイルをアップロード
                client.files_upload_v2(
                    channel=self.channel,  # チャンネルID
                    file=self.path,  # ファイルパス
                    title=self.title,  # ファイルタイトル
                    thread_ts=self.ts,
                )
                logger.info("File upload successful")
            except Exception as e:
                logger.error(f"File upload failed: {e}")
                # ファイルアップロードが失敗してもメッセージのtsは返す
            return message_ts

        except SlackApiError as e:
            logger.info(f"Got an error: {e.response['error']}")
            return ""
        except Exception as e:
            logger.info(f"Got an error: {e}")
            raise RuntimeError(f"Got an error: {e}") from e


if __name__ == "__main__":
    settings = get_settings()

    # 1. 新規メッセージを投稿
    slack = SlackContents(
        status=Status.RUNNING,
        title="Calibration Started",
        msg="Starting qubit calibration...",
        ts="",  # 新規メッセージなのでts空
        path="",
        header="Calibration Process",
        channel=settings.slack_channel_id,  # チャンネルID
        token=settings.slack_bot_token,
    )
    parent_ts = slack.send_slack()
    print(f"Parent message ts: {parent_ts}")

    # 2. スレッド内に進捗メッセージを投稿
    slack.update_contents(
        status=Status.RUNNING,
        title="Step 1",
        msg="Performing frequency calibration...",
        ts=parent_ts,  # 親メッセージのtsを指定してスレッド内に投稿
        broadcast=False,  # チャンネルには表示しない
    )
    slack.send_slack()

    # 3. スレッド内にファイルを添付
    slack.update_contents(
        status=Status.SUCCESS,
        title="Calibration Result",
        msg="Frequency calibration completed",
        ts=parent_ts,  # 同じスレッド内
        path="",  # 結果ファイル
        broadcast=False,  # チャンネルには表示しない
    )
    slack.send_slack()

    # 4. スレッド内に完了メッセージを投稿（チャンネルにも表示）
    slack.update_contents(
        status=Status.SUCCESS,
        title="Calibration Completed",
        msg="All calibration steps completed successfully",
        ts=parent_ts,  # 同じスレッド内
        path="",
        broadcast=True,  # チャンネルにも表示
    )
    slack.send_slack()
