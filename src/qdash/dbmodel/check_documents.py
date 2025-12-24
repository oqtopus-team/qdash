"""Diagnostic script to check QubitDocument and CouplingDocument data.

Run with:
    python -m qdash.dbmodel.check_documents
"""

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def check_documents() -> None:
    """Check QubitDocument and CouplingDocument collections."""
    from qdash.dbmodel.chip import ChipDocument
    from qdash.dbmodel.coupling import CouplingDocument
    from qdash.dbmodel.qubit import QubitDocument

    # Check ChipDocument
    logger.info("=" * 60)
    logger.info("ChipDocument")
    logger.info("=" * 60)
    chips = list(ChipDocument.find_all().run())
    logger.info(f"Total chips: {len(chips)}")
    for chip in chips[:5]:
        logger.info(
            f"  chip_id={chip.chip_id}, project_id={chip.project_id}, username={chip.username}"
        )

    # Check QubitDocument
    logger.info("")
    logger.info("=" * 60)
    logger.info("QubitDocument")
    logger.info("=" * 60)
    qubits = list(QubitDocument.find_all().run())
    logger.info(f"Total qubits: {len(qubits)}")

    # Group by project_id and chip_id
    qubit_groups: dict[tuple[str | None, str], int] = {}
    for q in qubits:
        key = (q.project_id, q.chip_id)
        qubit_groups[key] = qubit_groups.get(key, 0) + 1

    for (project_id, chip_id), count in list(qubit_groups.items())[:10]:
        logger.info(f"  project_id={project_id}, chip_id={chip_id}: {count} qubits")

    # Show sample qubit data
    if qubits:
        sample = qubits[0]
        logger.info("\nSample qubit:")
        logger.info(f"  qid={sample.qid}")
        logger.info(f"  project_id={sample.project_id}")
        logger.info(f"  chip_id={sample.chip_id}")
        logger.info(f"  username={sample.username}")
        logger.info(f"  data keys={list(sample.data.keys()) if sample.data else []}")

    # Check CouplingDocument
    logger.info("")
    logger.info("=" * 60)
    logger.info("CouplingDocument")
    logger.info("=" * 60)
    couplings = list(CouplingDocument.find_all().run())
    logger.info(f"Total couplings: {len(couplings)}")

    # Group by project_id and chip_id
    coupling_groups: dict[tuple[str | None, str], int] = {}
    for c in couplings:
        key = (c.project_id, c.chip_id)
        coupling_groups[key] = coupling_groups.get(key, 0) + 1

    for (project_id, chip_id), count in list(coupling_groups.items())[:10]:
        logger.info(f"  project_id={project_id}, chip_id={chip_id}: {count} couplings")

    # Check for mismatches
    logger.info("")
    logger.info("=" * 60)
    logger.info("Potential Issues")
    logger.info("=" * 60)

    chip_keys = {(c.project_id, c.chip_id) for c in chips}
    qubit_keys = set(qubit_groups.keys())
    coupling_keys = set(coupling_groups.keys())

    # Chips without qubits
    chips_without_qubits = chip_keys - qubit_keys
    if chips_without_qubits:
        logger.warning(f"Chips without QubitDocuments: {chips_without_qubits}")

    # Chips without couplings
    chips_without_couplings = chip_keys - coupling_keys
    if chips_without_couplings:
        logger.warning(f"Chips without CouplingDocuments: {chips_without_couplings}")

    # Qubits without chips
    qubits_without_chips = qubit_keys - chip_keys
    if qubits_without_chips:
        logger.warning(f"QubitDocuments without matching ChipDocument: {qubits_without_chips}")

    # Couplings without chips
    couplings_without_chips = coupling_keys - chip_keys
    if couplings_without_chips:
        logger.warning(
            f"CouplingDocuments without matching ChipDocument: {couplings_without_chips}"
        )

    if not (
        chips_without_qubits
        or chips_without_couplings
        or qubits_without_chips
        or couplings_without_chips
    ):
        logger.info("No mismatches found - all documents are consistent.")


if __name__ == "__main__":
    from qdash.dbmodel.initialize import initialize

    initialize()
    check_documents()
