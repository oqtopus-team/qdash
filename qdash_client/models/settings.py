from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

from typing import Union


T = TypeVar("T", bound="Settings")


@_attrs_define
class Settings:
    """Settings for the QDash application.

    Attributes:
        env (str):
        client_url (str):
        prefect_api_url (str):
        slack_bot_token (str):
        slack_channel_id (str):
        postgres_data_path (str):
        mongo_data_path (str):
        calib_data_path (str):
        qpu_data_path (str):
        slack_app_token (str):
        openai_api_key (str):
        backend (Union[Unset, str]):  Default: 'qubex'.
        mongo_port (Union[Unset, int]):  Default: 27017.
        mongo_express_port (Union[Unset, int]):  Default: 8081.
        postgres_port (Union[Unset, int]):  Default: 5432.
        prefect_port (Union[Unset, int]):  Default: 4200.
        api_port (Union[Unset, int]):  Default: 5715.
        ui_port (Union[Unset, int]):  Default: 5714.
        openai_model (Union[Unset, str]):  Default: 'o4-mini'.
        agent_max_steps (Union[Unset, int]):  Default: 10.
        log_level (Union[Unset, str]):  Default: 'INFO'.
    """

    env: str
    client_url: str
    prefect_api_url: str
    slack_bot_token: str
    slack_channel_id: str
    postgres_data_path: str
    mongo_data_path: str
    calib_data_path: str
    qpu_data_path: str
    slack_app_token: str
    openai_api_key: str
    backend: Union[Unset, str] = "qubex"
    mongo_port: Union[Unset, int] = 27017
    mongo_express_port: Union[Unset, int] = 8081
    postgres_port: Union[Unset, int] = 5432
    prefect_port: Union[Unset, int] = 4200
    api_port: Union[Unset, int] = 5715
    ui_port: Union[Unset, int] = 5714
    openai_model: Union[Unset, str] = "o4-mini"
    agent_max_steps: Union[Unset, int] = 10
    log_level: Union[Unset, str] = "INFO"

    def to_dict(self) -> dict[str, Any]:
        env = self.env

        client_url = self.client_url

        prefect_api_url = self.prefect_api_url

        slack_bot_token = self.slack_bot_token

        slack_channel_id = self.slack_channel_id

        postgres_data_path = self.postgres_data_path

        mongo_data_path = self.mongo_data_path

        calib_data_path = self.calib_data_path

        qpu_data_path = self.qpu_data_path

        slack_app_token = self.slack_app_token

        openai_api_key = self.openai_api_key

        backend = self.backend

        mongo_port = self.mongo_port

        mongo_express_port = self.mongo_express_port

        postgres_port = self.postgres_port

        prefect_port = self.prefect_port

        api_port = self.api_port

        ui_port = self.ui_port

        openai_model = self.openai_model

        agent_max_steps = self.agent_max_steps

        log_level = self.log_level

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "env": env,
                "client_url": client_url,
                "prefect_api_url": prefect_api_url,
                "slack_bot_token": slack_bot_token,
                "slack_channel_id": slack_channel_id,
                "postgres_data_path": postgres_data_path,
                "mongo_data_path": mongo_data_path,
                "calib_data_path": calib_data_path,
                "qpu_data_path": qpu_data_path,
                "slack_app_token": slack_app_token,
                "openai_api_key": openai_api_key,
            }
        )
        if backend is not UNSET:
            field_dict["backend"] = backend
        if mongo_port is not UNSET:
            field_dict["mongo_port"] = mongo_port
        if mongo_express_port is not UNSET:
            field_dict["mongo_express_port"] = mongo_express_port
        if postgres_port is not UNSET:
            field_dict["postgres_port"] = postgres_port
        if prefect_port is not UNSET:
            field_dict["prefect_port"] = prefect_port
        if api_port is not UNSET:
            field_dict["api_port"] = api_port
        if ui_port is not UNSET:
            field_dict["ui_port"] = ui_port
        if openai_model is not UNSET:
            field_dict["openai_model"] = openai_model
        if agent_max_steps is not UNSET:
            field_dict["agent_max_steps"] = agent_max_steps
        if log_level is not UNSET:
            field_dict["log_level"] = log_level

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        env = d.pop("env")

        client_url = d.pop("client_url")

        prefect_api_url = d.pop("prefect_api_url")

        slack_bot_token = d.pop("slack_bot_token")

        slack_channel_id = d.pop("slack_channel_id")

        postgres_data_path = d.pop("postgres_data_path")

        mongo_data_path = d.pop("mongo_data_path")

        calib_data_path = d.pop("calib_data_path")

        qpu_data_path = d.pop("qpu_data_path")

        slack_app_token = d.pop("slack_app_token")

        openai_api_key = d.pop("openai_api_key")

        backend = d.pop("backend", UNSET)

        mongo_port = d.pop("mongo_port", UNSET)

        mongo_express_port = d.pop("mongo_express_port", UNSET)

        postgres_port = d.pop("postgres_port", UNSET)

        prefect_port = d.pop("prefect_port", UNSET)

        api_port = d.pop("api_port", UNSET)

        ui_port = d.pop("ui_port", UNSET)

        openai_model = d.pop("openai_model", UNSET)

        agent_max_steps = d.pop("agent_max_steps", UNSET)

        log_level = d.pop("log_level", UNSET)

        settings = cls(
            env=env,
            client_url=client_url,
            prefect_api_url=prefect_api_url,
            slack_bot_token=slack_bot_token,
            slack_channel_id=slack_channel_id,
            postgres_data_path=postgres_data_path,
            mongo_data_path=mongo_data_path,
            calib_data_path=calib_data_path,
            qpu_data_path=qpu_data_path,
            slack_app_token=slack_app_token,
            openai_api_key=openai_api_key,
            backend=backend,
            mongo_port=mongo_port,
            mongo_express_port=mongo_express_port,
            postgres_port=postgres_port,
            prefect_port=prefect_port,
            api_port=api_port,
            ui_port=ui_port,
            openai_model=openai_model,
            agent_max_steps=agent_max_steps,
            log_level=log_level,
        )

        return settings
