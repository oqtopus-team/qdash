from datetime import datetime

from qdash.dbmodel.experiment import ExperimentModel


def put_experiment(experiment_name: str):
    experiment = ExperimentModel.find_one(ExperimentModel.experiment_name == experiment_name).run()

    if experiment is None:
        experiment = ExperimentModel(experiment_name=experiment_name)
        experiment.insert()
    else:
        experiment.updated_at = datetime.now()
        experiment.save()
