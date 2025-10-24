"""Deploy Python Flow examples for testing.

This script deploys the example flows to Prefect for testing purposes.
"""

from prefect import serve
from qdash.workflow.examples.adaptive_parallel_example import adaptive_parallel_example
from qdash.workflow.examples.parallel_calibration_example import (
    parallel_calibration_example,
)
from qdash.workflow.examples.smart_calibration import smart_calibration

if __name__ == "__main__":
    # Deploy parallel calibration example
    parallel_deploy = parallel_calibration_example.to_deployment(
        name="example-parallel-calibration",
        description="True parallel calibration using @task + submit()",
        tags=["example", "python-flow", "parallel"],
        parameters={
            "username": "orangekame3",
            "chip_id": "64Qv3",
            "qids": ["32", "38"],
        },
    )

    # Deploy adaptive parallel calibration example
    adaptive_deploy = adaptive_parallel_example.to_deployment(
        name="example-adaptive-parallel",
        description="Parallel adaptive calibration with custom convergence logic",
        tags=["example", "python-flow", "adaptive", "parallel"],
        parameters={
            "username": "orangekame3",
            "chip_id": "64Qv3",
            "qids": ["32", "38"],
            "threshold": 0.01,
            "max_iterations": 10,
        },
    )

    # Deploy smart calibration example
    smart_deploy = smart_calibration.to_deployment(
        name="example-smart-calibration",
        description="Smart calibration with conditional branching",
        tags=["example", "python-flow", "conditional"],
        parameters={
            "username": "test_user",
            "chip_id": "chip_1",
            "qids": ["0", "1"],
            "frequency_threshold": 5.0,
        },
    )

    # Serve all example deployments
    print("Deploying Python Flow examples...")
    print("Access Prefect UI at: http://localhost:4200")
    print("\nDeployed flows:")
    print("  - example-parallel-calibration")
    print("  - example-adaptive-parallel")
    print("  - example-smart-calibration")

    serve(
        parallel_deploy,  # type: ignore
        adaptive_deploy,  # type: ignore
        smart_deploy,  # type: ignore
        webserver=False,  # Don't start another webserver
        limit=10,
    )
