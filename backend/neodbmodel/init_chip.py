from neodbmodel.chip import ChipDocument
from repository.initialize import initialize


def init_chip_document():
    initialize()
    chip = ChipDocument(
        chip_id="SAMPLE",
        size=64,
        qubits={},
        couplings={},
        system_info={},
    )
    chip.save()
    return chip


if __name__ == "__main__":
    init_chip_document()
