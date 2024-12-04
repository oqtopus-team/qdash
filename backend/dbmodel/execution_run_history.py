from datetime import datetime
from typing import Optional

from bunnet import Document
from bunnet.odm.operators.update.general import Set
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from .one_qubit_calib_all_history import OneQubitCalibAllHistoryModel


class ExecutionRunHistoryModel(Document):
    date: str
    timestamp: datetime = Field(default_factory=datetime.now)
    status: Optional[str] = Field(None)
    execution_id: str
    updated_at: datetime = Field(default_factory=datetime.now)
    qpu_name: Optional[str] = Field(None)
    menu: dict
    tags: Optional[list[str]] = Field(None)
    fridge_temperature: Optional[float] = Field(None)
    flow_url: Optional[str] = Field(None)

    class Settings:
        name = "execution_run_history"
        indexes = [IndexModel([("execution_id", ASCENDING)], unique=True)]

    model_config = ConfigDict(
        from_attributes=True,
    )

    @classmethod
    def get_by_execution_id(cls, execution_id: str):
        return cls.find_one(cls.execution_id == execution_id).run()

    def add_tags(self, new_tags: list[str]):
        if self.tags is None:
            self.tags = new_tags
        else:
            # 重複していないタグのみを追加
            self.tags.extend(tag for tag in new_tags if tag not in self.tags)
        self.save()

        # OneQubitCalibAllHistoryModel の対応するドキュメントを更新
        histories = OneQubitCalibAllHistoryModel.find(
            OneQubitCalibAllHistoryModel.execution_id == self.execution_id
        )
        for history in histories:
            history.update(Set({OneQubitCalibAllHistoryModel.tags: self.tags}))

    def remove_tags(self, tags_to_remove: list[str]):
        if self.tags is not None:
            self.tags = [tag for tag in self.tags if tag not in tags_to_remove]
        self.save()

        # OneQubitCalibAllHistoryModel の対応するドキュメントを更新
        histories = OneQubitCalibAllHistoryModel.find(
            OneQubitCalibAllHistoryModel.execution_id == self.execution_id
        )
        for history in histories:
            history.update(Set({OneQubitCalibAllHistoryModel.tags: self.tags}))
