"""Manager for dynamically creating and managing Prefect deployments for user flows."""

import importlib.util
import sys
from pathlib import Path

from prefect.deployments import Deployment


class DeploymentManager:
    """Manager for user flow deployments."""

    @staticmethod
    def create_deployment(
        file_path: str,
        flow_name: str,
        deployment_name: str | None = None,
    ) -> str:
        """Create a Prefect deployment from a user flow file.

        Args:
        ----
            file_path: Path to the Python file containing the flow
            flow_name: Name of the flow function to deploy
            deployment_name: Name for the deployment (defaults to flow_name)

        Returns:
        -------
            Deployment ID

        """
        file_path_obj = Path(file_path).resolve()

        if not file_path_obj.exists():
            raise FileNotFoundError(f"Flow file not found: {file_path}")

        # Dynamically import the flow module
        module_name = f"user_flow_{file_path_obj.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path_obj)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module from {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Get the flow object
        if not hasattr(module, flow_name):
            raise AttributeError(f"Flow '{flow_name}' not found in {file_path}")

        flow_obj = getattr(module, flow_name)

        # Create deployment
        if deployment_name is None:
            deployment_name = flow_name

        deployment = Deployment.build_from_flow(
            flow=flow_obj,
            name=deployment_name,
            work_pool_name="default-agent-pool",  # Use default work pool
            path=str(file_path_obj.parent),
        )

        # Apply deployment to Prefect Server
        deployment_id = deployment.apply()

        return deployment_id

    @staticmethod
    def delete_deployment(deployment_id: str) -> None:
        """Delete a deployment.

        Args:
        ----
            deployment_id: ID of the deployment to delete

        """
        # TODO: Implement deployment deletion using Prefect client
        pass
