#!/usr/bin/env python3
"""
QDash Modern Python Client Examples

This module demonstrates how to use the generated modern Python client
for QDash quantum calibration workflows with async/await, Pydantic models,
and httpx integration.
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Any

# Import the generated client (after running: generate-python-client)
try:
    from qdash.client import Client, AuthenticatedClient
    from qdash.client.api import *
    from qdash.client.models import *
    from qdash.client.errors import UnexpectedStatus
except ImportError as e:
    print("❌ QDash client not found!")
    print("First generate the client: generate-python-client")
    print(
        "Or install QDash with client dependencies: pip install 'git+https://github.com/oqtopus-team/qdash.git[client]'"
    )
    print(f"Error details: {e}")
    exit(1)


class QuantumCalibrationWorkflow:
    """Example quantum calibration workflow using the modern Python client."""

    def __init__(self, base_url: str = "http://localhost:5715"):
        self.base_url = base_url

    async def run_parallel_calibrations(self, chip_ids: List[str]) -> Dict[str, Any]:
        """
        Run calibrations on multiple chips in parallel.

        Args:
            chip_ids: List of quantum chip IDs to calibrate

        Returns:
            Dictionary of calibration results by chip ID
        """
        print(f"🚀 Starting parallel calibrations for {len(chip_ids)} chips...")

        async with AsyncApiClient(base_url=self.base_url) as client:
            # Start calibrations concurrently
            calibration_tasks = []

            for chip_id in chip_ids:
                # Create calibration request with Pydantic validation
                calibration_request = {
                    "chip_id": chip_id,
                    "experiment_type": "rabi_oscillation",
                    "parameters": {
                        "frequency_start": 5.0e9,
                        "frequency_stop": 5.5e9,
                        "amplitude_start": 0.01,
                        "amplitude_stop": 0.1,
                        "num_points": 50,
                    },
                    "metadata": {
                        "operator": "quantum-engineer",
                        "timestamp": datetime.now().isoformat(),
                        "workflow": "parallel_calibration",
                    },
                }

                # Start calibration (async)
                task = client.calibration_start_calibration_post(json_body=calibration_request)
                calibration_tasks.append((chip_id, task))

            # Wait for all calibrations to start
            results = {}
            for chip_id, task in calibration_tasks:
                try:
                    result = await task
                    results[chip_id] = result
                    print(f"✅ Started calibration for chip {chip_id}: {result.id}")
                except Exception as e:
                    print(f"❌ Failed to start calibration for chip {chip_id}: {e}")
                    results[chip_id] = {"error": str(e)}

            return results

    async def monitor_calibration_progress(self, calibration_id: str) -> None:
        """
        Monitor calibration progress with real-time updates.

        Args:
            calibration_id: ID of the calibration to monitor
        """
        print(f"👁️  Monitoring calibration {calibration_id}...")

        async with AsyncApiClient(base_url=self.base_url) as client:
            while True:
                try:
                    # Get current status
                    status = await client.calibration_get_calibration_status_get(
                        calibration_id=calibration_id
                    )

                    print(f"📊 Calibration {calibration_id}: {status.status} ({status.progress}%)")

                    if status.status in ["completed", "failed", "cancelled"]:
                        print(f"🏁 Calibration finished with status: {status.status}")
                        if status.status == "completed":
                            # Get results
                            results = await client.calibration_get_calibration_results_get(
                                calibration_id=calibration_id
                            )
                            print(f"📈 Results available: {len(results.measurements)} measurements")
                        break

                    # Wait before next check
                    await asyncio.sleep(2)

                except Exception as e:
                    print(f"❌ Error monitoring calibration: {e}")
                    break

    async def quantum_parameter_optimization(self, chip_id: str) -> Dict[str, Any]:
        """
        Advanced example: Quantum parameter optimization workflow.

        Args:
            chip_id: Quantum chip to optimize

        Returns:
            Optimization results
        """
        print(f"🎯 Starting parameter optimization for chip {chip_id}...")

        async with AsyncApiClient(base_url=self.base_url) as client:
            # 1. Get current chip parameters
            chip_info = await client.chip_get_chip_get(chip_id=chip_id)
            current_params = chip_info.parameters
            print(f"📋 Current parameters: frequency={current_params.qubit_frequency}")

            # 2. Run T1 measurement to establish baseline
            t1_request = {
                "chip_id": chip_id,
                "experiment_type": "t1_measurement",
                "parameters": {
                    "delay_start": 0,
                    "delay_stop": 100e-6,  # 100 microseconds
                    "num_points": 20,
                    "measurement_count": 1000,
                },
            }

            t1_calibration = await client.calibration_start_calibration_post(json_body=t1_request)
            print(f"🔬 Started T1 measurement: {t1_calibration.id}")

            # Monitor T1 completion
            await self._wait_for_completion(client, t1_calibration.id)

            # 3. Get T1 results
            t1_results = await client.calibration_get_calibration_results_get(
                calibration_id=t1_calibration.id
            )
            t1_time = t1_results.analysis.get("t1_time", 50e-6)  # fallback
            print(f"📊 T1 time measured: {t1_time*1e6:.1f} μs")

            # 4. Run frequency sweep around current frequency
            freq_sweep_request = {
                "chip_id": chip_id,
                "experiment_type": "qubit_spectroscopy",
                "parameters": {
                    "frequency_center": current_params.qubit_frequency,
                    "frequency_span": 10e6,  # ±10 MHz
                    "num_points": 100,
                    "power": -20,  # dBm
                },
            }

            freq_calibration = await client.calibration_start_calibration_post(
                json_body=freq_sweep_request
            )
            print(f"🔍 Started frequency sweep: {freq_calibration.id}")

            await self._wait_for_completion(client, freq_calibration.id)

            # 5. Analyze and update optimal frequency
            freq_results = await client.calibration_get_calibration_results_get(
                calibration_id=freq_calibration.id
            )
            optimal_frequency = freq_results.analysis.get("optimal_frequency")

            if optimal_frequency:
                # Update chip parameters
                updated_params = {
                    **current_params.dict(),
                    "qubit_frequency": optimal_frequency,
                    "last_calibration": datetime.now().isoformat(),
                }

                await client.chip_update_chip_parameters_put(
                    chip_id=chip_id, json_body=updated_params
                )
                print(f"✅ Updated chip frequency: {optimal_frequency/1e9:.6f} GHz")

            return {
                "chip_id": chip_id,
                "t1_time": t1_time,
                "original_frequency": current_params.qubit_frequency,
                "optimized_frequency": optimal_frequency,
                "improvement": abs(optimal_frequency - current_params.qubit_frequency)
                if optimal_frequency
                else 0,
            }

    async def _wait_for_completion(self, client: AsyncApiClient, calibration_id: str) -> None:
        """Helper method to wait for calibration completion."""
        while True:
            status = await client.calibration_get_calibration_status_get(
                calibration_id=calibration_id
            )

            if status.status in ["completed", "failed", "cancelled"]:
                break

            await asyncio.sleep(1)


class SyncQuantumWorkflow:
    """Example synchronous quantum workflow for simpler use cases."""

    def __init__(self, base_url: str = "http://localhost:5715"):
        self.base_url = base_url

    def get_chip_summary(self, chip_id: str) -> Dict[str, Any]:
        """
        Get a summary of chip status and recent calibrations.

        Args:
            chip_id: Quantum chip ID

        Returns:
            Chip summary dictionary
        """
        with ApiClient(base_url=self.base_url) as client:
            # Get chip info
            chip = client.chip_get_chip_get(chip_id=chip_id)

            # Get recent calibrations
            history = client.calibration_get_calibration_history_get(chip_id=chip_id, limit=5)

            # Calculate summary stats
            recent_calibrations = len(history.items)
            success_rate = (
                sum(1 for cal in history.items if cal.status == "completed") / recent_calibrations
                if recent_calibrations > 0
                else 0
            )

            return {
                "chip_id": chip_id,
                "status": chip.status,
                "qubit_count": len(chip.qubits),
                "recent_calibrations": recent_calibrations,
                "success_rate": success_rate,
                "last_calibration": history.items[0].created_at if history.items else None,
                "current_frequency": chip.parameters.qubit_frequency,
            }


async def main():
    """Main example runner."""
    print("🌟 QDash Modern Python Client Examples")
    print("=" * 50)

    # Initialize workflow
    workflow = QuantumCalibrationWorkflow()
    sync_workflow = SyncQuantumWorkflow()

    try:
        # Example 1: Parallel calibrations
        print("\n📡 Example 1: Parallel Calibrations")
        chip_ids = ["chip-001", "chip-002", "chip-003"]
        results = await workflow.run_parallel_calibrations(chip_ids)
        print(f"Started calibrations: {len(results)} chips")

        # Example 2: Monitor a calibration
        if results and any(isinstance(r, dict) and "id" in r for r in results.values()):
            calibration_id = next(
                r["id"] for r in results.values() if isinstance(r, dict) and "id" in r
            )
            print(f"\n👁️  Example 2: Monitor Calibration {calibration_id}")
            await workflow.monitor_calibration_progress(calibration_id)

        # Example 3: Parameter optimization
        print("\n🎯 Example 3: Parameter Optimization")
        optimization_result = await workflow.quantum_parameter_optimization("chip-001")
        print(f"Optimization completed: {optimization_result}")

        # Example 4: Sync workflow
        print("\n📊 Example 4: Synchronous Chip Summary")
        summary = sync_workflow.get_chip_summary("chip-001")
        print(f"Chip summary: {summary}")

    except Exception as e:
        print(f"❌ Example failed: {e}")
        print("Make sure QDash API is running and client is generated!")


if __name__ == "__main__":
    asyncio.run(main())
