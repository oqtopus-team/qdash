"""Folding a System-named chip into its physical chip."""

from typing import Any

import mongomock
import pytest

from qdash.dbmodel.merge_chip_systems import merge_chip_systems


def _seed(source: Any, target: Any) -> None:
    target["chip"].insert_one({"project_id": "p", "chip_id": "144Qv3"})
    source["chip"].insert_one({"project_id": "p", "chip_id": "144Qv3-quel3"})
    for qid in ("0", "1", "24", "25"):
        target["qubit"].insert_one(
            {
                "project_id": "p",
                "chip_id": "144Qv3",
                "qid": qid,
                "data": {"t1": 1} if qid == "0" else {},
            }
        )
        source["qubit"].insert_one(
            {
                "project_id": "p",
                "chip_id": "144Qv3-quel3",
                "qid": qid,
                "data": {"t1": 9} if qid in ("24", "25") else {},
            }
        )
    source["qubit"].insert_one(
        {"project_id": "p", "chip_id": "144Qv3-quel3", "qid": "26", "data": {"t1": 3}}
    )
    source["task_result_history"].insert_many(
        [
            {"project_id": "p", "chip_id": "144Qv3-quel3", "task_id": "t-1", "qid": "24"},
            {
                "project_id": "p",
                "chip_id": "144Qv3-quel3",
                "task_id": "t-2",
                "qid": "25",
                "system_id": "x",
            },
        ]
    )
    target["task_result_history"].create_index([("project_id", 1), ("task_id", 1)], unique=True)
    target["task_result_history"].insert_one(
        {"project_id": "p", "chip_id": "144Qv3", "task_id": "t-1"}
    )
    source["execution_lock"].insert_one({"project_id": "p", "chip_id": "144Qv3-quel3"})
    source["cooldown"].insert_one({"project_id": "p", "chip_ids": ["144Qv3-quel3"]})


def test_dry_run_reports_without_writing() -> None:
    client: Any = mongomock.MongoClient()
    source, target = client["quel3"], client["main"]
    _seed(source, target)

    report = merge_chip_systems(
        source, target, from_chip="144Qv3-quel3", to_chip="144Qv3", qids=["24", "25", "26"]
    )

    assert report["apply"] is False
    assert report["collections"]["qubit"] == {
        "matched": 5,
        "replaced": 2,
        "inserted": 1,
        "skipped": 2,
    }
    assert report["collections"]["task_result_history"]["matched"] == 2
    assert "execution_lock" not in report["collections"]
    assert target["qubit"].find_one({"qid": "24"})["data"] == {}


def test_apply_replaces_owned_qubits_and_copies_history_once() -> None:
    client: Any = mongomock.MongoClient()
    source, target = client["quel3"], client["main"]
    _seed(source, target)

    report = merge_chip_systems(
        source,
        target,
        from_chip="144Qv3-quel3",
        to_chip="144Qv3",
        qids=["24", "25", "26"],
        apply=True,
    )

    assert target["qubit"].find_one({"qid": "24"})["data"] == {"t1": 9}
    assert target["qubit"].find_one({"qid": "0"})["data"] == {"t1": 1}
    assert target["qubit"].find_one({"qid": "26"})["chip_id"] == "144Qv3"
    assert target["qubit"].count_documents({"chip_id": "144Qv3"}) == 5
    history = report["collections"]["task_result_history"]
    assert history == {"matched": 2, "inserted": 1, "duplicates": 1}
    copied = target["task_result_history"].find_one({"task_id": "t-2"})
    assert copied["chip_id"] == "144Qv3" and copied["system_id"] == "x"
    assert source["chip"].find_one({"chip_id": "144Qv3-quel3"}) is not None
    assert target["cooldown"].count_documents({}) == 0


def test_same_database_renames_in_place_and_stamps_system_id() -> None:
    client: Any = mongomock.MongoClient()
    db = client["main"]
    db["chip"].insert_one({"project_id": "p", "chip_id": "144Qv3"})
    db["task_result_history"].insert_one(
        {"project_id": "p", "chip_id": "144Qv3-quel3", "task_id": "t-9", "qid": "24"}
    )

    merge_chip_systems(db, db, from_chip="144Qv3-quel3", to_chip="144Qv3", qids=["24"], apply=True)

    doc = db["task_result_history"].find_one({"task_id": "t-9"})
    assert doc["chip_id"] == "144Qv3" and doc["system_id"] == "144Qv3-quel3"


def test_refuses_without_target_chip_or_same_names() -> None:
    client: Any = mongomock.MongoClient()
    db = client["main"]
    with pytest.raises(ValueError, match="does not exist"):
        merge_chip_systems(db, db, from_chip="a", to_chip="b", qids=[])
    db["chip"].insert_one({"chip_id": "a"})
    with pytest.raises(ValueError, match="must differ"):
        merge_chip_systems(db, db, from_chip="a", to_chip="a", qids=[])
