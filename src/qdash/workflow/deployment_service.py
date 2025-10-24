"""Minimal HTTP service for registering Prefect deployments from user flows.

This service runs in the Workflow container and provides a single endpoint
to register user flows as Prefect deployments.
"""

from logging import getLogger
from pathlib import Path

from fastapi import FastAPI, HTTPException
from prefect.client.orchestration import get_client
from prefect.deployments import Deployment
from pydantic import BaseModel

app = FastAPI(title="QDash Deployment Service")
logger = getLogger("uvicorn.app")

# Work pool name for user flows
WORK_POOL_NAME = "user-flows-pool"


class RegisterDeploymentRequest(BaseModel):
    """Request to register a deployment."""

    file_path: str
    flow_function_name: str
    deployment_name: str | None = None
    old_deployment_id: str | None = None


class RegisterDeploymentResponse(BaseModel):
    """Response from deployment registration."""

    deployment_id: str
    deployment_name: str


@app.post("/register-deployment", response_model=RegisterDeploymentResponse)
async def register_deployment(request: RegisterDeploymentRequest) -> RegisterDeploymentResponse:
    """Register a user flow as a Prefect deployment.

    Args:
    ----
        request: Registration request with file path and flow name

    Returns:
    -------
        Deployment ID and name

    """
    try:
        file_path = Path(request.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Flow file not found: {file_path}")

        # Create deployment name
        deployment_name = request.deployment_name or request.flow_function_name

        logger.info(f"Creating deployment '{deployment_name}' from {file_path}")

        # Create entrypoint string: relative_path:function_name
        # Working directory is /app/qdash/workflow, so make path relative to that
        working_dir = Path("/app/qdash/workflow")
        try:
            relative_path = file_path.relative_to(working_dir)
        except ValueError:
            # If file is not under working_dir, use absolute path
            relative_path = file_path

        entrypoint = f"{relative_path}:{request.flow_function_name}"

        logger.info(f"Using entrypoint: {entrypoint}")

        # Load flow to validate it exists
        import importlib.util

        spec = importlib.util.spec_from_file_location("temp_module", file_path)
        if spec is None or spec.loader is None:
            raise HTTPException(status_code=400, detail=f"Could not load module from {file_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, request.flow_function_name):
            raise HTTPException(
                status_code=400, detail=f"Flow function '{request.flow_function_name}' not found in {file_path}"
            )

        flow_obj = getattr(module, request.flow_function_name)

        # Delete old deployment if it exists
        if request.old_deployment_id:
            try:
                async with get_client() as client:
                    await client.delete_deployment(request.old_deployment_id)
                    logger.info(f"Deleted old deployment: {request.old_deployment_id}")
            except Exception as e:
                logger.warning(f"Failed to delete old deployment: {e}")

        # Build deployment using the flow object with work pool
        deployment = await Deployment.build_from_flow(
            flow=flow_obj,
            name=deployment_name,
            work_pool_name=WORK_POOL_NAME,
            entrypoint=entrypoint,
            path=str(working_dir),
        )

        # Apply to Prefect Server
        deployment_id = await deployment.apply()

        logger.info(f"Deployment created: {deployment_id}")

        return RegisterDeploymentResponse(
            deployment_id=str(deployment_id),
            deployment_name=deployment_name,
        )

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except AttributeError as e:
        logger.error(f"Flow function not found: {e}")
        raise HTTPException(status_code=400, detail=f"Flow function '{request.flow_function_name}' not found")
    except Exception as e:
        logger.error(f"Failed to register deployment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}
