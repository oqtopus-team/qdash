"""Flow repository implementation."""

from datetime import datetime
from typing import Any

from qdash.dbmodel.flow import FlowDocument


class MongoFlowRepository:
    """MongoDB implementation of Flow repository."""

    def find_by_user_and_name(
        self, username: str, name: str, project_id: str
    ) -> FlowDocument | None:
        """Find flow by username and name.

        Args:
            username: Username of the flow owner
            name: Flow name
            project_id: Project identifier

        Returns:
            FlowDocument if found, None otherwise
        """
        return FlowDocument.find_by_user_and_name(username, name, project_id)  # type: ignore[no-any-return]

    def list_by_user(self, username: str, project_id: str) -> list[FlowDocument]:
        """List all flows for a user, sorted by update time (newest first).

        Args:
            username: Username of the flow owner
            project_id: Project identifier

        Returns:
            List of FlowDocument objects
        """
        return FlowDocument.list_by_user(username, project_id)  # type: ignore[no-any-return]

    def insert(self, flow: FlowDocument) -> None:
        """Insert a new flow document.

        Args:
            flow: Flow document to insert
        """
        flow.insert()

    def save(self, flow: FlowDocument) -> None:
        """Save (update) an existing flow document.

        Args:
            flow: Flow document to save
        """
        flow.save()

    def delete_by_user_and_name(self, username: str, name: str, project_id: str) -> bool:
        """Delete flow by username and name.

        Args:
            username: Username of the flow owner
            name: Flow name
            project_id: Project identifier

        Returns:
            True if deleted, False if not found
        """
        return FlowDocument.delete_by_user_and_name(username, name, project_id)  # type: ignore[no-any-return]

    def create_flow(
        self,
        project_id: str,
        name: str,
        username: str,
        chip_id: str,
        description: str,
        flow_function_name: str,
        default_parameters: dict[str, Any],
        file_path: str,
        deployment_id: str,
        tags: list[str],
        default_run_parameters: dict[str, Any] | None = None,
    ) -> FlowDocument:
        """Create a new flow document.

        Args:
            project_id: Project identifier
            name: Flow name
            username: Owner username
            chip_id: Target chip ID
            description: Flow description
            flow_function_name: Entry point function name
            default_parameters: Default parameters for execution
            file_path: Path to .py file
            deployment_id: Prefect deployment ID
            tags: Tags for categorization
            default_run_parameters: Default run parameters for all tasks

        Returns:
            Created FlowDocument
        """
        flow_doc = FlowDocument(
            project_id=project_id,
            name=name,
            username=username,
            chip_id=chip_id,
            description=description,
            flow_function_name=flow_function_name,
            default_parameters=default_parameters,
            default_run_parameters=default_run_parameters or {},
            file_path=file_path,
            deployment_id=deployment_id,
            tags=tags,
        )
        flow_doc.insert()
        return flow_doc

    def update_flow(
        self,
        flow: FlowDocument,
        description: str | None = None,
        chip_id: str | None = None,
        flow_function_name: str | None = None,
        default_parameters: dict[str, Any] | None = None,
        default_run_parameters: dict[str, Any] | None = None,
        file_path: str | None = None,
        deployment_id: str | None = None,
        tags: list[str] | None = None,
    ) -> FlowDocument:
        """Update an existing flow document.

        Args:
            flow: Flow document to update
            description: New description (optional)
            chip_id: New chip ID (optional)
            flow_function_name: New function name (optional)
            default_parameters: New parameters (optional)
            default_run_parameters: New run parameters (optional)
            file_path: New file path (optional)
            deployment_id: New deployment ID (optional)
            tags: New tags (optional)

        Returns:
            Updated FlowDocument
        """
        if description is not None:
            flow.description = description
        if chip_id is not None:
            flow.chip_id = chip_id
        if flow_function_name is not None:
            flow.flow_function_name = flow_function_name
        if default_parameters is not None:
            flow.default_parameters = default_parameters
        if default_run_parameters is not None:
            flow.default_run_parameters = default_run_parameters
        if file_path is not None:
            flow.file_path = file_path
        if deployment_id is not None:
            flow.deployment_id = deployment_id
        if tags is not None:
            flow.tags = tags
        flow.updated_at = datetime.now()
        flow.save()
        return flow

    def find_one(self, query: dict[str, Any]) -> FlowDocument | None:
        """Find a single flow document by query.

        Args:
            query: MongoDB query dict

        Returns:
            FlowDocument if found, None otherwise
        """
        return FlowDocument.find_one(query).run()
