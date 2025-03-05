import logging
from datetime import datetime, timedelta

import pytz
from dbmodel.bluefors import BlueforsModel
from fastapi import APIRouter
from fastapi.logger import logger
from pydantic import BaseModel

router = APIRouter()


# class ResponseModel(BaseModel):
#     message: str


gunicorn_logger = logging.getLogger("gunicorn.error")
logger.handlers = gunicorn_logger.handlers


# @router.get("/fridges/", response_model=ResponseModel)
# def health():
#     return {"message": "Hello World"}


class ListAllFridgeResponse(BaseModel):
    device_id: str


@router.get("/fridges/", response_model=ListAllFridgeResponse)
def list_all_fridges():
    return {"device_id": "XLD"}


class ListFridgeResponse(BaseModel):
    timestamp: datetime
    temperature: float


@router.get("/fridges/XLD/channels/{channel}", response_model=list[ListFridgeResponse])
def get_fridge_temperature(channel: int, h: float = 12.0):
    time = datetime.now() - timedelta(hours=h)
    jst = pytz.timezone("Asia/Tokyo")
    history = (
        BlueforsModel.find(BlueforsModel.channel_nr == channel, BlueforsModel.timestamp > time)
        .sort([BlueforsModel.timestamp])
        .project(ListFridgeResponse)
        .to_list()
    )
    # 温度を小数点4桁にフォーマット
    for record in history:
        record.timestamp = record.timestamp.astimezone(jst)
        record.temperature = round(record.temperature, 4)

    return history
