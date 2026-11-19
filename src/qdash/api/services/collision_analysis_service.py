"""Load chip calibration data and run frequency collision checks."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

from starlette.exceptions import HTTPException

from qdash.api.schemas.collision_analysis import (
    CollisionCellResponse,
    CollisionCheckInfo,
    CollisionCheckItem,
    CollisionEvaluateRequest,
    CollisionEvaluateResponse,
    CollisionParameterInfo,
    LegendEntry,
    ListCollisionChecksResponse,
)
from qdash.api.services.collision_analysis import (
    CHECKS,
    CheckDefinition,
    CollisionContext,
    CollisionTopology,
    Measurement,
    QubitPair,
    evaluate_check,
    qid,
    resolve_params,
)
from qdash.common.config.topology import load_topology
from qdash.common.utils.datetime import now

if TYPE_CHECKING:
    from qdash.repository.chip import MongoChipRepository

logger = logging.getLogger(__name__)

# (parameter read by the checks, stored keys in priority order, unit assumed when absent)
QUBIT_PARAMETERS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("qubit_frequency", ("qubit_frequency",), "GHz"),
    ("resonator_frequency", ("resonator_frequency",), "GHz"),
    ("qubit_anharmonicity", ("qubit_anharmonicity", "anharmonicity"), "GHz"),
    ("t1", ("t1",), "us"),
    ("t2_echo", ("t2_echo",), "us"),
)
COUPLING_KEYS: tuple[str, ...] = ("qubit_qubit_coupling_strength", "coupling_strength")
COUPLING_DEFAULT_UNIT = "MHz"


def _finite(value: float | None) -> float | None:
    return value if value is not None and math.isfinite(value) else None


def _measurement(data: dict[str, Any], keys: tuple[str, ...], default_unit: str) -> Measurement:
    """Return the first usable stored value.

    None, zero (NaN may have been stored as 0) and non-finite values count as missing.
    Returns ``(None, default_unit)`` when no key holds a usable value.
    """
    for key in keys:
        entry = data.get(key)
        if isinstance(entry, dict):
            raw = entry.get("value")
            unit = entry.get("unit")
        else:
            raw, unit = entry, None
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        number = float(raw)
        if not math.isfinite(number) or number == 0:
            continue
        return number, unit if isinstance(unit, str) and unit.strip() else default_unit
    return None, default_unit


def _check_info(definition: CheckDefinition) -> CollisionCheckInfo:
    return CollisionCheckInfo(
        kind=definition.kind,
        title=definition.title,
        description=definition.description,
        target=definition.target,
        unit=definition.unit,
        parameters=[
            CollisionParameterInfo(
                name=name,
                default=p.default,
                min=p.min,
                unit=p.unit,
                label=p.label or name,
            )
            for name, p in definition.parameters.items()
        ],
        legend=[LegendEntry(color=color, label=label) for color, label in definition.legend],
    )


class CollisionAnalysisService:
    """Run collision checks against a chip's latest calibration data."""

    def __init__(self, chip_repository: MongoChipRepository) -> None:
        self._chips = chip_repository

    def list_checks(self) -> ListCollisionChecksResponse:
        return ListCollisionChecksResponse(
            checks=[_check_info(definition) for definition in CHECKS.values()]
        )

    def _topology(self, project_id: str, chip_id: str) -> CollisionTopology:
        chip = self._chips.find_one_document({"project_id": project_id, "chip_id": chip_id})
        if chip is None:
            raise HTTPException(status_code=404, detail=f"Chip '{chip_id}' not found")
        if not chip.topology_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Chip '{chip_id}' has no topology; set its topology to run collision analysis"
                ),
            )
        try:
            definition = load_topology(chip.topology_id)
        except Exception as exc:
            logger.warning("Failed to load topology %s: %s", chip.topology_id, exc)
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Topology '{chip.topology_id}' of chip '{chip_id}' could not be loaded; "
                    "collision analysis needs a valid topology"
                ),
            ) from exc
        return CollisionTopology.from_definition(definition)

    def _context(
        self,
        project_id: str,
        chip_id: str,
        topology: CollisionTopology,
        params: dict[str, float],
    ) -> CollisionContext:
        data: dict[str, dict[str, Measurement]] = {name: {} for name, _, _ in QUBIT_PARAMETERS}
        for raw_qid, qubit in self._chips.get_all_qubit_models(project_id, chip_id).items():
            try:
                q = qid(raw_qid)
            except ValueError:
                continue
            for name, keys, default_unit in QUBIT_PARAMETERS:
                value, unit = _measurement(qubit.data, keys, default_unit)
                if value is not None:
                    data[name][q] = (value, unit)
        couplings: dict[str, Measurement] = {}
        for raw_key, coupling in self._chips.get_all_coupling_models(project_id, chip_id).items():
            ends = raw_key.split("-")
            if len(ends) != 2:
                continue
            try:
                key = f"{qid(ends[0])}-{qid(ends[1])}"
            except ValueError:
                continue
            value, unit = _measurement(coupling.data, COUPLING_KEYS, COUPLING_DEFAULT_UNIT)
            if value is not None:
                couplings[key] = (value, unit)
        return CollisionContext(topology=topology, params=params, data=data, couplings=couplings)

    def evaluate(
        self, *, project_id: str, chip_id: str, body: CollisionEvaluateRequest
    ) -> CollisionEvaluateResponse:
        definition = CHECKS.get(body.check)
        if definition is None:
            known = ", ".join(CHECKS)
            raise HTTPException(
                status_code=422,
                detail=f"Unknown collision check '{body.check}'; expected one of: {known}",
            )
        try:
            params = resolve_params(body.check, body.params)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        hops = sorted(set(body.hops))
        if not hops or not set(hops) <= {1, 2}:
            raise HTTPException(status_code=422, detail="hops must be a non-empty subset of [1, 2]")

        topology = self._topology(project_id, chip_id)
        ctx = self._context(project_id, chip_id, topology, params)
        cells = []
        for cell in evaluate_check(body.check, ctx, hops=hops):
            result, target = cell.result, cell.target
            pair = target if isinstance(target, QubitPair) else None
            cells.append(
                CollisionCellResponse(
                    key=cell.key,
                    qid=None if pair else str(target),
                    source=pair.source if pair else None,
                    target=pair.target if pair else None,
                    hops=pair.hops if pair else None,
                    value=_finite(result.value),
                    color=result.color,
                    label=result.assessment["label"],
                    checks=[
                        CollisionCheckItem(label=label, value=_finite(value))
                        for label, value in result.assessment["checks"]
                    ],
                    estimates=list(result.assessment["estimates"]),
                )
            )
        return CollisionEvaluateResponse(
            chip_id=chip_id,
            check=definition.kind,
            title=definition.title,
            description=definition.description,
            target=definition.target,
            unit=definition.unit,
            legend=[LegendEntry(color=color, label=label) for color, label in definition.legend],
            parameters=params,
            cells=cells,
            evaluated_at=now(),
        )
