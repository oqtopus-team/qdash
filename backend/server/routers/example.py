from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..lib.current_user import get_current_user_id

router = APIRouter(
    prefix="/example",
    tags=["example"],
)


class ExampleResponse(BaseModel):
    message: str
    user_id: str


@router.get("", response_model=ExampleResponse)
def get_example(
    current_user_id: Annotated[str, Depends(get_current_user_id)],
) -> ExampleResponse:
    """現在のユーザーIDを使用するエンドポイントの例

    Parameters
    ----------
    current_user_id : str
        現在のユーザーID (Dependencyから自動的に取得)

    Returns
    -------
    ExampleResponse
        レスポンス

    """
    return ExampleResponse(
        message="This is an example endpoint",
        user_id=current_user_id,
    )


@router.post("/create")
def create_something(
    current_user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict:
    """データ作成時にユーザーIDを保存する例

    Parameters
    ----------
    current_user_id : str
        現在のユーザーID (Dependencyから自動的に取得)

    Returns
    -------
    dict
        作成されたデータ

    """
    # 例: データベースにデータを保存する際にuser_idを含める
    data = {
        "content": "Some data",
        "user_id": current_user_id,
        # その他のフィールド
    }

    return data
