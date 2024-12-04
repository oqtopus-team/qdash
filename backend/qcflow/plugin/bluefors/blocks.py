from prefect.blocks.core import Block


class BlueforsBlock(Block):
    bluefors_server_url: str = ""
    mongo_url: str = ""
    mongo_database: str = ""
    mongo_collection: str = ""
