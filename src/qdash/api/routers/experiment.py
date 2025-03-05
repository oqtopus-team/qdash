from fastapi import APIRouter
from pydantic import BaseModel
from qdash.dbmodel.experiment import ExperimentModel

router = APIRouter()


class ExperimentResponse(BaseModel):
    experiment_name: str
    updated_at: str


@router.get(
    "/experiments",
    response_model=list[ExperimentResponse],
    summary="Fetch all experiments",
    operation_id="fetch_all_experiment",
)
def fetch_all_experiment():
    experiments = ExperimentModel.find_all()
    return [
        ExperimentResponse(
            experiment_name=exp.experiment_name,
            updated_at=exp.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        )
        for exp in experiments
    ]
