from neodbmodel.initialize import initialize
from neodbmodel.menu import MenuDocument

if __name__ == "__main__":
    initialize()
    menu = MenuDocument(
        name="OneQubitCheck",
        username="admin",
        description="description",
        qids=[["28", "29", "30", "31"]],
        tasks=["CheckStatus", "DumpBox", "CheckNoise", "CheckRabi"],
        notify_bool=False,
        tags=["tag1", "tag2"],
        system_info={},
    ).insert()
