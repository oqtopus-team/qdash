"""Backend-independent resolution of declared inputs from calibration records."""

from collections.abc import Mapping
from typing import Any

from qdash.datamodel.task import InputParameterModel, InputParameterSpec, ParameterModel


def populate_parameters(
    input_parameters: dict[str, Any],
    declarations: Mapping[str, Any],
    role_data_sources: dict[str, list[dict[str, Any]]],
) -> None:
    declarations = declarations or input_parameters
    for param_name, declaration in declarations.items():
        param = input_parameters[param_name]
        # Determine the DB lookup key
        if (
            isinstance(declaration, (InputParameterSpec, ParameterModel))
            and declaration.parameter_name
        ):
            lookup_key = declaration.parameter_name
        else:
            lookup_key = param_name

        # Determine the qid_role for source selection
        qid_role = ""
        if isinstance(declaration, (InputParameterSpec, ParameterModel)):
            qid_role = declaration.qid_role

        # Get the ordered list of data sources for this role
        sources = role_data_sources.get(qid_role, role_data_sources.get("", []))

        primary_lookup_keys: tuple[str, ...] = (lookup_key,)
        fallback_lookup_keys: tuple[str, ...] = ()
        if isinstance(declaration, InputParameterSpec):
            primary_lookup_keys += declaration.parameter_aliases
            fallback_lookup_keys = declaration.fallback_parameter_names

        # Preserve source priority for equivalent names, but only use semantic
        # fallbacks when no canonical name or alias exists in any source.
        db_value = None
        resolved_parameter_name = lookup_key
        value_found = False
        for lookup_keys in (primary_lookup_keys, fallback_lookup_keys):
            for source in sources:
                for candidate_key in lookup_keys:
                    if candidate_key in source:
                        db_value = source[candidate_key]
                        resolved_parameter_name = candidate_key
                        value_found = True
                        break
                if value_found:
                    break
            if value_found:
                break

        if db_value is not None:
            if isinstance(db_value, dict):
                if isinstance(declaration, InputParameterSpec):
                    if declaration.resolution == "default_only":
                        continue
                    input_parameters[param_name] = InputParameterModel(
                        parameter_name=resolved_parameter_name,
                        qid_role=declaration.qid_role,
                        value=db_value.get("value", declaration.default),
                        value_type=declaration.value_type,
                        unit=db_value.get("unit", declaration.unit),
                        description=db_value.get("description", declaration.description),
                        ui_group=declaration.ui_group,
                        ui_group_collapsed=declaration.ui_group_collapsed,
                        calibrated_at=db_value.get("calibrated_at", param.calibrated_at),
                        execution_id=db_value.get("execution_id", ""),
                        task_id=db_value.get("task_id", ""),
                    )
                elif declaration is None:
                    # Create ParameterModel entirely from DB
                    input_parameters[param_name] = ParameterModel(
                        value=db_value.get("value", 0),
                        unit=db_value.get("unit", ""),
                        description=db_value.get("description", ""),
                    )
                else:
                    # Update existing ParameterModel with DB value
                    if "value" in db_value:
                        param.value = db_value["value"]
                    for metadata_name in (
                        "unit",
                        "description",
                        "calibrated_at",
                        "execution_id",
                        "task_id",
                    ):
                        if metadata_name in db_value:
                            setattr(param, metadata_name, db_value[metadata_name])
        elif isinstance(declaration, InputParameterSpec):
            if declaration.resolution == "database_required":
                raise ValueError(
                    f"Required input parameter '{lookup_key}' for role "
                    f"'{qid_role or 'self'}' was not found in the calibration database"
                )
            # The instance was initialized with the explicit default value.
        elif (
            isinstance(declaration, ParameterModel)
            and declaration.source == "database"
            and declaration.required
        ):
            raise ValueError(
                f"Required input parameter '{lookup_key}' for role "
                f"'{qid_role or 'self'}' was not found in the calibration database"
            )
        elif declaration is None:
            # Deprecated compatibility behavior for legacy declarations.
            input_parameters[param_name] = ParameterModel(
                unit="",
                description=f"Parameter {param_name} not found in DB",
            )
