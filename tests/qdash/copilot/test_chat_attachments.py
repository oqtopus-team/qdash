"""Validate image attachments before chat and analysis requests reach the runtime."""

import base64

import pytest
from pydantic import ValidationError

from qdash.copilot.contracts.models import AnalyzeRequest, ChatImageAttachment, ChatRequest

PNG = b"\x89PNG\r\n\x1a\n"
JPEG = b"\xff\xd8\xff"


@pytest.mark.parametrize("mime,header", [("image/png", PNG), ("image/jpeg", JPEG)])
def test_accepts_matching_base64_image(mime: str, header: bytes) -> None:
    """Both wire aliases and Python field names validate the declared format."""
    data = base64.b64encode(header).decode()
    for key in ("mimeType", "mime_type"):
        image = ChatImageAttachment.model_validate({"data": data, key: mime})
        assert image.model_dump(by_alias=True) == {"data": data, "mimeType": mime}


@pytest.mark.parametrize("data", ["!!!", "YQ==", base64.b64encode(JPEG).decode(), "é"])
def test_rejects_invalid_base64_or_mismatched_bytes(data: str) -> None:
    """Invalid payloads never pass the request model as PNG images."""
    with pytest.raises(ValidationError):
        ChatImageAttachment.model_validate({"data": data, "mimeType": "image/png"})


def test_rejects_oversized_single_image() -> None:
    """The single-image limit applies even to valid base64 with the correct signature."""
    data = base64.b64encode(PNG + b"x" * (5 * 1024 * 1024)).decode()
    with pytest.raises(ValidationError):
        ChatImageAttachment.model_validate({"data": data, "mimeType": "image/png"})


@pytest.mark.parametrize("request_type", [ChatRequest, AnalyzeRequest])
def test_total_budget_applies_to_both_chat_surfaces(
    request_type: type[ChatRequest] | type[AnalyzeRequest],
) -> None:
    """Individually valid images cannot exceed the aggregate runtime budget."""
    data = base64.b64encode(PNG + b"x" * (3 * 1024 * 1024 - len(PNG))).decode()
    image = {"data": data, "mimeType": "image/png"}
    common = {
        "message": "Evaluate",
        "task_name": "CheckT1",
        "chip_id": "c",
        "qid": "0",
        "execution_id": "e",
        "task_id": "t",
    }
    assert len(request_type.model_validate({**common, "images": [image] * 3}).images) == 3
    with pytest.raises(ValidationError, match="12 MiB"):
        request_type.model_validate({**common, "images": [image] * 4})
