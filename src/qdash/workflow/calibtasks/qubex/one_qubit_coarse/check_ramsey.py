from typing import Any, ClassVar

import plotly.graph_objects as go
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS
from qdash.workflow.engine.calibration.task.types import TaskTypes


class CheckRamsey(QubexTask):
    """Task to check the Rabi oscillation."""

    name: str = "CheckRamsey"
    task_type = TaskTypes.QUBIT
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "detuning": InputParameterModel(
            unit="GHz",
            value_type="float",
            value=0.001,
            description="Detuning for Ramsey oscillation",
        ),
        "time_range": InputParameterModel(
            unit="ns",
            value_type="np.arange",
            value=(0, 10001, 100),
            description="Time range for Rabi oscillation",
        ),
        "shots": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": InputParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "ramsey_frequency": OutputParameterModel(
            unit="MHz", description="Ramsey oscillation frequency"
        ),
        "qubit_frequency": OutputParameterModel(unit="GHz", description="Qubit bare frequency"),
        "t2_star": OutputParameterModel(unit="μs", description="T2* time"),
    }

    def make_figure(self, result_x: Any, result_y: Any, label: str) -> go.Figure:
        """Create a figure for the results."""
        x_data = result_x.normalized.astype(float)
        y_data = result_y.normalized.astype(float)
        sweep = result_x.sweep_range.astype(float)

        # 色を sweep の逆順でカラーマップ化
        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=x_data,
                y=y_data,
                mode="markers+lines",
                marker={
                    "size": 6,
                    "color": sweep[::-1],
                    "colorscale": "Viridis",
                    "line": {"width": 0.5, "color": "DarkSlateGrey"},
                },
                text=[f"sweep: {s:.0f} ns" for s in sweep],
                hoverinfo="text+x+y",
                showlegend=False,
            )
        )

        fig.update_layout(
            title=f"Ramsey Interference in XY Plane : {label}",
            xaxis={
                "title": "⟨X⟩",
                "scaleanchor": "y",
                "scaleratio": 1,
                "showgrid": True,
                "gridcolor": "lightgray",
                "zeroline": True,
                "zerolinecolor": "gray",
            },
            yaxis={
                "title": "⟨Y⟩",
                "scaleanchor": "x",
                "scaleratio": 1,
                "showgrid": True,
                "gridcolor": "lightgray",
                "zeroline": True,
                "zerolinecolor": "gray",
            },
            width=700,
            height=700,
            plot_bgcolor="white",
            hovermode="closest",
            showlegend=False,
        )

        return fig

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        # Check if results contain the expected label
        from prefect import get_run_logger

        logger = get_run_logger()

        # Debug: Check what labels are actually in the data
        x_labels = (
            list(run_result.raw_result["x"].data.keys())
            if hasattr(run_result.raw_result["x"], "data")
            else []
        )
        y_labels = (
            list(run_result.raw_result["y"].data.keys())
            if hasattr(run_result.raw_result["y"], "data")
            else []
        )

        logger.info(f"Expected label: {label}")
        logger.info(f"X-axis data labels: {x_labels}")
        logger.info(f"Y-axis data labels: {y_labels}")

        # Check if label exists in results
        has_x_data = label in run_result.raw_result["x"].data
        has_y_data = label in run_result.raw_result["y"].data

        if not has_x_data and not has_y_data:
            raise KeyError(
                f"Label '{label}' not found in either X or Y axis results. "
                f"X-axis labels: {x_labels}, Y-axis labels: {y_labels}. "
                f"Both experiments failed to run or returned no data."
            )

        # Handle cases where only one axis has data
        if not has_x_data:
            logger.warning(f"X-axis experiment failed for {label}, will use Y-axis data only")
            result_x = None
        else:
            result_x = run_result.raw_result["x"].data[label]

        if not has_y_data:
            logger.warning(f"Y-axis experiment failed for {label}, will use X-axis data only")
            result_y = None
        else:
            result_y = run_result.raw_result["y"].data[label]

        # Determine which fit was successful based on R2
        # R2 is used to determine if fit was successful (not exceptions)
        # Handle cases where one or both experiments failed
        x_fit = result_x.fit() if result_x is not None else None
        y_fit = result_y.fit() if result_y is not None else None

        x_r2 = result_x.r2 if result_x is not None and hasattr(result_x, "r2") else None
        y_r2 = result_y.r2 if result_y is not None and hasattr(result_y, "r2") else None

        # Log R2 values for debugging
        logger.info(f"CheckRamsey fit results for Q{qid}:")
        x_r2_str = f"{x_r2:.4f}" if x_r2 is not None else "N/A (no data)"
        y_r2_str = f"{y_r2:.4f}" if y_r2 is not None else "N/A (no data)"
        logger.info(f"  X-axis R²: {x_r2_str}")
        logger.info(f"  Y-axis R²: {y_r2_str}")
        logger.info(f"  R² threshold: {self.r2_threshold:.4f}")

        # Check if fit succeeded based on R2 threshold
        # A fit is considered successful if R2 is above the threshold
        x_fit_success = x_r2 is not None and not self.r2_is_lower_than_threshold(x_r2)
        y_fit_success = y_r2 is not None and not self.r2_is_lower_than_threshold(y_r2)

        x_fit_status = (
            "✓ Success" if x_fit_success else ("✗ Failed" if result_x is not None else "✗ No data")
        )
        y_fit_status = (
            "✓ Success" if y_fit_success else ("✗ Failed" if result_y is not None else "✗ No data")
        )
        logger.info(f"  X-axis fit: {x_fit_status}")
        logger.info(f"  Y-axis fit: {y_fit_status}")

        # Choose the best result:
        # 1. If both succeed, prefer the one with higher R2
        # 2. If only one succeeds, use that one
        # 3. If neither succeeds, use the one with higher R2 (for figure saving)
        #    and let the R2 check in TaskManager raise the error later
        if x_fit_success and y_fit_success:
            # Both succeeded - choose based on R2
            if x_r2 is not None and y_r2 is not None:
                use_x = x_r2 >= y_r2
            else:
                use_x = True  # Default to X if R2 not available
        elif x_fit_success:
            use_x = True
        elif y_fit_success:
            use_x = False
        else:
            # Both failed - use the one with higher R2 for figure saving
            # The error will be raised by TaskManager's R2 check after figures are saved
            if x_r2 is not None and y_r2 is not None:
                use_x = x_r2 >= y_r2
            else:
                use_x = True  # Default to X

        # Use the selected result
        if use_x:
            selected_result = result_x
            selected_fit = x_fit
            selected_axis = "X"
        else:
            selected_result = result_y
            selected_fit = y_fit
            selected_axis = "Y"

        selected_r2 = (
            x_r2
            if use_x and x_r2 is not None
            else (y_r2 if not use_x and y_r2 is not None else None)
        )
        selected_r2_str = f"{selected_r2:.4f}" if selected_r2 is not None else "N/A"
        logger.info(f"  Selected axis: {selected_axis} (R²={selected_r2_str})")

        # Ensure we have valid results before proceeding
        if selected_result is None:
            raise ValueError(
                f"No valid Ramsey result available for Q{qid}. "
                "Both X and Y axis experiments returned no data."
            )
        if selected_fit is None:
            raise ValueError(
                f"No valid Ramsey fit available for Q{qid}. " "Fit failed for the selected axis."
            )

        logger.info(f"  Bare frequency: {selected_result.bare_freq:.6f} GHz")

        self.output_parameters["ramsey_frequency"].value = (
            selected_fit["f"] * 1000
        )  # convert to MHz
        self.output_parameters["ramsey_frequency"].error = selected_fit["f_err"] * 1000
        self.output_parameters["qubit_frequency"].value = selected_result.bare_freq
        self.output_parameters["t2_star"].value = selected_result.t2 * 0.001  # convert to μs
        self.output_parameters["t2_star"].error = selected_fit["tau_err"] * 0.001  # convert to μs
        output_parameters = self.attach_execution_id(execution_id)

        # Always include all available figures (regardless of fit success)
        # Even if fits failed (low R2), the figures are still useful for debugging
        figures = []
        if x_fit is not None:
            figures.append(x_fit["fig"])
        if y_fit is not None:
            figures.append(y_fit["fig"])
        # Only create XY plane figure if both X and Y data are available
        if result_x is not None and result_y is not None:
            figures.append(self.make_figure(result_x, result_y, label))

        raw_data = [selected_result.data]
        return PostProcessResult(
            output_parameters=output_parameters, figures=figures, raw_data=raw_data
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        # Apply frequency override if qubit_frequency was explicitly provided
        with self._apply_frequency_override(backend, qid):
            result_y = exp.ramsey_experiment(
                time_range=self.input_parameters["time_range"].get_value(),
                shots=self.input_parameters["shots"].get_value(),
                interval=self.input_parameters["interval"].get_value(),
                detuning=self.input_parameters["detuning"].get_value(),
                second_rotation_axis="Y",  # Default axis for Ramsey
                spectator_state="0",
                targets=label,
            )
            result_x = exp.ramsey_experiment(
                time_range=self.input_parameters["time_range"].get_value(),
                shots=self.input_parameters["shots"].get_value(),
                interval=self.input_parameters["interval"].get_value(),
                detuning=self.input_parameters["detuning"].get_value(),
                second_rotation_axis="X",  # Default axis for Ramsey
                spectator_state="0",
                targets=label,
            )

        self.save_calibration(backend)
        result = {"x": result_x, "y": result_y}

        # Debug: Log what data was returned
        from prefect import get_run_logger

        logger = get_run_logger()
        logger.info(f"Ramsey experiment completed for Q{qid}")
        logger.info(f"  X-axis result type: {type(result_x)}")
        logger.info(f"  Y-axis result type: {type(result_y)}")
        if hasattr(result_x, "data"):
            logger.info(f"  X-axis data keys: {list(result_x.data.keys())}")
        if hasattr(result_y, "data"):
            logger.info(f"  Y-axis data keys: {list(result_y.data.keys())}")

        # Get R2 from both X and Y, and use the higher one
        # This ensures that if one fit succeeds, the task is not marked as failed
        x_r2 = None
        y_r2 = None
        if result_x.data and hasattr(result_x.data[label], "r2"):
            x_r2 = result_x.data[label].r2
        if result_y.data and hasattr(result_y.data[label], "r2"):
            y_r2 = result_y.data[label].r2

        # Choose the higher R2 value
        if x_r2 is not None and y_r2 is not None:
            r2 = max(x_r2, y_r2)
        elif x_r2 is not None:
            r2 = x_r2
        elif y_r2 is not None:
            r2 = y_r2
        else:
            r2 = None

        return RunResult(raw_result=result, r2={qid: r2})
