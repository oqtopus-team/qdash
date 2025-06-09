import itertools
import json
from collections import defaultdict

import networkx as nx
from qdash.datamodel.qubit import QubitModel
from qdash.db.init import initialize
from qdash.dbmodel.chip import ChipDocument


def get_two_qubit_pair_list(chip_doc: ChipDocument) -> list[str]:
    """Get a list of two-qubit coupling IDs for a given chip and user.

    Args:
    ----
        chip_id (str): The ID of the chip.
        username (str): The username of the user.

    Returns:
    -------
        list[str]: A list of two-qubit coupling IDs.

    """
    two_qubit_list = [
        coupling_id
        for coupling_id in chip_doc.couplings.keys()
        if "-" in coupling_id and len(coupling_id.split("-")) == 2
    ]

    return two_qubit_list


def cr_pair_list(two_qubit_list: list[str], bare_freq: dict[str, float]) -> list[str]:
    """Get a list of two-qubit coupling IDs where first qubit frequency is lower than second qubit frequency.

    Args:
    ----
        two_qubit_list (list[str]): List of two-qubit coupling IDs.
        bare_freq (dict[str, float]): Dictionary of bare frequencies keyed by qubit ID.

    Returns:
    -------
        list[str]: A list of two-qubit coupling IDs where first qubit has lower frequency.

    """
    filtered_pairs = []
    for coupling_id in two_qubit_list:
        q1, q2 = coupling_id.split("-")
        if q1 in bare_freq and q2 in bare_freq:
            if bare_freq[q1] < bare_freq[q2]:
                filtered_pairs.append(coupling_id)
    return filtered_pairs


def get_other_cr_pairs(cr_pairs: list[str], mux_groups: list[list[int]]) -> list[str]:
    """Get CR pairs that don't belong to any of the specified mux groups.

    Args:
    ----
        cr_pairs (list[str]): List of CR pairs where first qubit has lower frequency.
        mux_groups (list[list[int]]): List of mux groups to exclude.

    Returns:
    -------
        list[str]: List of CR pairs that don't belong to any mux group.

    """
    # Get all pairs that belong to any mux group
    mux_pairs = set()
    for mux_group in mux_groups:
        pairs = filter_cr_pairs_by_mux(cr_pairs, mux_group)
        mux_pairs.update(pairs)

    # Return pairs that aren't in any mux group
    return [pair for pair in cr_pairs if pair not in mux_pairs]


def filter_cr_pairs_by_mux(cr_pairs: list[str], mux_list: list[int]) -> list[str]:
    """Filter CR pairs to only include pairs where both qubits belong to specified mux numbers.

    Args:
    ----
        cr_pairs (list[str]): List of CR pairs where first qubit has lower frequency.
        mux_list (list[int]): List of mux numbers to filter by.

    Returns:
    -------
        list[str]: List of CR pairs where both qubits belong to the specified mux numbers.

    """
    # Create a mapping of qubit ID to mux number
    qubit_to_mux = {}
    for qid in range(64):  # Assuming 64 qubits total
        mux_num = qid // 4  # Each mux has 4 qubits
        if mux_num in mux_list:
            qubit_to_mux[str(qid)] = mux_num

    # Filter CR pairs where both qubits belong to specified mux numbers
    filtered_pairs = []
    for pair in cr_pairs:
        q1, q2 = pair.split("-")
        if q1 in qubit_to_mux and q2 in qubit_to_mux:
            filtered_pairs.append(pair)

    return filtered_pairs


def extract_bare_frequency(qubits: dict[str, QubitModel]) -> dict[str, float]:
    """Extract bare frequency values from qubit data.

    Args:
    ----
        qubits: Dictionary of qubit models keyed by qubit ID

    Returns:
    -------
        Dictionary of bare frequency values keyed by qubit ID

    """
    result = {}
    for qid, qubit in qubits.items():
        if qubit.data and "bare_frequency" in qubit.data:
            result[qid] = qubit.data["bare_frequency"]["value"]
    return result


if __name__ == "__main__":
    # Example usage
    username = "admin"
    initialize()
    chip_doc = ChipDocument.get_current_chip(username)
    two_qubit_list = get_two_qubit_pair_list(chip_doc)

    bare_freq = extract_bare_frequency(chip_doc.qubits)
    print(two_qubit_list)
    print(len(two_qubit_list), "couplings found.")
    print(bare_freq)

    # Get CR pairs where first qubit frequency is lower than second qubit frequency
    cr_pairs = cr_pair_list(two_qubit_list, bare_freq)
    print("\nCR pairs (low freq -> high freq):")
    print(cr_pairs)
    print(len(cr_pairs), "CR pairs found.")

    # Filter CR pairs by mux groups
    # mux_groups = [[0, 1, 4, 5], [2, 3, 6, 7], [8, 9, 12, 13], [10, 11, 14, 15]]
    mux_groups = [[0, 1, 10, 11, 14, 15], [2, 3, 6, 7], [4, 5, 8, 9, 12, 13]]
    # mux_groups = [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]]
    internal_schedule = {"parallel": []}
    for mux_group in mux_groups:
        filtered_pairs = filter_cr_pairs_by_mux(cr_pairs, mux_group)
        print("\nCR pairs where both qubits belong to mux numbers", mux_group, ":")
        print(filtered_pairs)
        print(len(filtered_pairs), "filtered pairs found.")
        internal_schedule["parallel"].append({"serial": filtered_pairs})

    external_schedule = {"parallel": []}
    # Get CR pairs that don't belong to any mux group
    other_pairs = get_other_cr_pairs(cr_pairs, mux_groups)
    print("\n" + "=" * 40)
    print("🧩 CR pairs that don't belong to any mux group")
    print("=" * 40)
    print(f"Count: {len(other_pairs)}")
    print("Pairs:", other_pairs)

    external_schedule["parallel"].append({"serial": other_pairs})

    print("\n" + "=" * 40)
    print("📦 Internal Schedule")
    print("=" * 40)
    print(json.dumps(internal_schedule, indent=2))

    print("\n" + "=" * 40)
    print("🌐 External Schedule")
    print("=" * 40)
    print(json.dumps(external_schedule, indent=2))
