"""Records as QDash wrote them before automatic calibration sessions existed.

An agent session created without a calibration session now gets an automatic one. Tests of
behavior that legacy records keep (a standalone agent session row, an agent session that
relates no calibration session) turn a freshly created session back into such a record.
"""

from __future__ import annotations

from qdash.dbmodel.agent_session import AgentSessionDocument
from qdash.dbmodel.calibration_session import CalibrationSessionDocument


def make_standalone_agent_session(project_id: str, session_id: str) -> None:
    """Strip an agent session's automatic calibration session, as before the upgrade."""
    doc = AgentSessionDocument.find_one({"project_id": project_id, "session_id": session_id}).run()
    assert doc is not None
    parent = doc.calibration_session_id
    AgentSessionDocument.get_motor_collection().update_one(
        {"project_id": project_id, "session_id": session_id},
        {
            "$set": {
                "calibration_session_id": None,
                "calibration_admission": None,
                "calibration_reservation_id": None,
            }
        },
    )
    if parent:
        CalibrationSessionDocument.get_motor_collection().delete_one(
            {"project_id": project_id, "calibration_session_id": parent, "origin": "automatic"}
        )
