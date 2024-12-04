from functools import lru_cache

from pydantic_settings import BaseSettings  # , SettingsConfigDict


class Settings(BaseSettings):
    env: str
    client_url: str
    prefect_api_url: str
    slack_bot_token: str
    postgres_data_path: str
    mongo_data_path: str
    calib_data_path: str
    mongo_host: str
    prefect_host: str
    postgres_host: str
    qpu_data_path: str


@lru_cache()
def get_settings():
    return Settings()  # type: ignore
