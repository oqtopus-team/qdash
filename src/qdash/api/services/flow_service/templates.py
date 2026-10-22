"""Catalog of flow templates and helper files shipped with the workflow service."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException

from qdash.api.schemas.flow import FlowTemplate, FlowTemplateWithCode
from qdash.common.config.path_resolver import (
    resolve_workflow_service_dir,
    resolve_workflow_templates_dir,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("uvicorn.app")


class TemplateCatalog:
    """Load flow templates and helper files from the workflow tree."""

    def __init__(
        self,
        templates_dir: Path | None = None,
        helpers_dir: Path | None = None,
    ) -> None:
        self._templates_dir = templates_dir or resolve_workflow_templates_dir()
        self._helpers_dir = helpers_dir or resolve_workflow_service_dir()

    @property
    def metadata_file(self) -> Path:
        """Path of the template index describing each template file."""
        return self._templates_dir / "templates.json"

    def list_templates(self) -> list[FlowTemplate]:
        """List template metadata, or an empty list when no index exists."""
        try:
            if not self.metadata_file.exists():
                logger.error(f"Templates metadata file not found: {self.metadata_file}")
                return []

            templates_data = json.loads(self.metadata_file.read_text(encoding="utf-8"))
            templates = [FlowTemplate(**template) for template in templates_data]
            logger.info(f"Listed {len(templates)} flow templates")
            return templates
        except Exception as exc:
            logger.error(f"Failed to list flow templates: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list flow templates: {exc}",
            ) from exc

    def get_template(self, template_id: str) -> FlowTemplateWithCode:
        """Return one template together with its flow source."""
        try:
            if not self.metadata_file.exists():
                raise HTTPException(status_code=404, detail="Templates metadata file not found")

            templates_data = json.loads(self.metadata_file.read_text(encoding="utf-8"))
            template_data = next(
                (template for template in templates_data if template["id"] == template_id),
                None,
            )
            if not template_data:
                raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

            code_file = self._templates_dir / template_data["filename"]
            if not code_file.exists():
                logger.error(f"Template file not found: {code_file}")
                raise HTTPException(status_code=404, detail=f"Template file not found: {code_file}")

            code = code_file.read_text(encoding="utf-8")
            return FlowTemplateWithCode(**template_data, code=code)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Failed to get flow template: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get flow template: {exc}",
            ) from exc

    def list_helper_files(self) -> list[str]:
        """List the Python helper modules importable from a user flow."""
        try:
            if not self._helpers_dir.exists():
                logger.warning(f"Flow helpers directory not found: {self._helpers_dir}")
                return []

            files = [
                helper.name
                for helper in self._helpers_dir.iterdir()
                if helper.is_file() and helper.suffix == ".py" and not helper.name.startswith("_")
            ]
            if (self._helpers_dir / "__init__.py").exists():
                files.insert(0, "__init__.py")

            files = sorted(set(files), key=lambda name: (name != "__init__.py", name))
            logger.info(f"Listed {len(files)} flow helper files")
            return files
        except Exception as exc:
            logger.error(f"Failed to list flow helper files: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list flow helper files: {exc}",
            ) from exc

    def get_helper_file(self, filename: str) -> str:
        """Return the source of one helper module."""
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        if not filename.endswith(".py"):
            raise HTTPException(status_code=400, detail="Only Python files are allowed")

        file_path = self._helpers_dir / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error(f"Failed to read flow helper file {filename}: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read file: {exc}",
            ) from exc

        logger.info(f"Read flow helper file: {filename}")
        return content
