"""Tests for API dependency providers."""

from qdash.api import dependencies


def _clear_dependency_caches() -> None:
    dependencies.get_activity_repository.cache_clear()
    dependencies.get_coupling_calibration_repository.cache_clear()
    dependencies.get_manual_update_service.cache_clear()
    dependencies.get_parameter_version_repository.cache_clear()
    dependencies.get_provenance_relation_repository.cache_clear()
    dependencies.get_provenance_service.cache_clear()
    dependencies.get_qubit_calibration_repository.cache_clear()
    dependencies.get_seed_import_service.cache_clear()
    dependencies.get_user_repository.cache_clear()


def test_provenance_services_use_shared_repository_providers() -> None:
    _clear_dependency_caches()

    parameter_version_repo = dependencies.get_parameter_version_repository()
    provenance_relation_repo = dependencies.get_provenance_relation_repository()
    activity_repo = dependencies.get_activity_repository()
    user_repo = dependencies.get_user_repository()

    provenance_service = dependencies.get_provenance_service()
    seed_import_service = dependencies.get_seed_import_service()
    manual_update_service = dependencies.get_manual_update_service()

    assert provenance_service.parameter_version_repo is parameter_version_repo
    assert provenance_service.provenance_relation_repo is provenance_relation_repo
    assert provenance_service.activity_repo is activity_repo
    assert seed_import_service._param_version_repo is parameter_version_repo
    assert seed_import_service._relation_repo is provenance_relation_repo
    assert seed_import_service._activity_repo is activity_repo
    assert seed_import_service._user_repository is user_repo
    assert manual_update_service._param_version_repo is parameter_version_repo
    assert manual_update_service._relation_repo is provenance_relation_repo
    assert manual_update_service._activity_repo is activity_repo


def test_manual_update_service_uses_calibration_repository_providers() -> None:
    _clear_dependency_caches()

    qubit_repo = dependencies.get_qubit_calibration_repository()
    coupling_repo = dependencies.get_coupling_calibration_repository()

    service = dependencies.get_manual_update_service()

    assert service._qubit_repo is qubit_repo
    assert service._coupling_repo is coupling_repo
