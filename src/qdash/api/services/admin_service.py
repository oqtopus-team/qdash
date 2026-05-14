"""Admin service for user and project management."""

from __future__ import annotations

import csv
import logging
import secrets
from io import StringIO
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from qdash.api.lib.auth import get_password_hash
from qdash.api.schemas.admin import (
    BulkUserImportResponse,
    BulkUserImportResult,
    MemberItem,
    MemberListResponse,
    ProjectListItem,
    ProjectListResponse,
    UserDetailResponse,
    UserListItem,
    UserListResponse,
)
from qdash.api.services.auth_service import generate_temporary_password
from qdash.common.utils.datetime import now
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import (
    USERNAME_PATTERN_DESCRIPTION,
    SystemRole,
    generate_user_id,
    is_valid_username,
)
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qdash.datamodel.project import ProjectRole


MAX_BULK_IMPORT_ROWS = 500
REQUIRED_BULK_IMPORT_COLUMNS = {"username"}
SUPPORTED_BULK_IMPORT_COLUMNS = {
    "username",
    "display_name",
    "organization",
    "system_role",
}


class AdminService:
    """Service for admin user and project management operations."""

    @staticmethod
    def _user_id_for_username(username: str | None) -> str | None:
        """Resolve a username to a user_id for new relationship writes."""
        if not username:
            return None
        user = UserDocument.find_one({"username": username}).run()
        return user.user_id if user else None

    @staticmethod
    def _user_to_detail(user: UserDocument) -> UserDetailResponse:
        """Convert a UserDocument to UserDetailResponse."""
        return UserDetailResponse(
            user_id=user.user_id,
            username=user.username,
            display_name=user.display_name,
            organization=user.organization,
            avatar_key=user.avatar_key,
            disabled=user.disabled,
            system_role=user.system_role,
            default_project_id=user.default_project_id,
            must_change_password=user.must_change_password,
            created_at=user.system_info.created_at if user.system_info else None,
            updated_at=user.system_info.updated_at if user.system_info else None,
        )

    # --- User Management ---

    @staticmethod
    def _parse_system_role(value: str | None) -> SystemRole:
        """Parse system role from CSV."""
        if value is None or value.strip() == "":
            return SystemRole.USER
        try:
            return SystemRole(value.strip().lower())
        except ValueError as exc:
            raise ValueError(f"Invalid system_role '{value}'") from exc

    @staticmethod
    def _bulk_result(
        row_number: int,
        row: Mapping[str, str],
        status_value: str,
        message: str | None = None,
        initial_password: str | None = None,
        system_role: SystemRole = SystemRole.USER,
    ) -> BulkUserImportResult:
        """Build a result row for bulk import."""
        return BulkUserImportResult(
            row_number=row_number,
            username=(row.get("username") or "").strip(),
            display_name=(row.get("display_name") or "").strip() or None,
            organization=(row.get("organization") or "").strip() or None,
            system_role=system_role,
            initial_password=initial_password,
            status=status_value,
            message=message,
        )

    def bulk_import_users(self, csv_content: str) -> BulkUserImportResponse:
        """Create users from CSV and return generated temporary passwords."""
        stream = StringIO(csv_content)
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV header is required",
            )

        fieldnames = {field.strip() for field in reader.fieldnames if field}
        missing = REQUIRED_BULK_IMPORT_COLUMNS - fieldnames
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required columns: {', '.join(sorted(missing))}",
            )

        unsupported = fieldnames - SUPPORTED_BULK_IMPORT_COLUMNS
        if unsupported:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported columns: {', '.join(sorted(unsupported))}",
            )

        results: list[BulkUserImportResult] = []

        for index, raw_row in enumerate(reader, start=2):
            if len(results) >= MAX_BULK_IMPORT_ROWS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"CSV row limit exceeded: maximum {MAX_BULK_IMPORT_ROWS}",
                )

            row = {key.strip(): (value or "").strip() for key, value in raw_row.items() if key}
            username = row.get("username", "")
            if not username:
                results.append(self._bulk_result(index, row, "failed", "username is required"))
                continue
            if not is_valid_username(username):
                results.append(
                    self._bulk_result(index, row, "failed", USERNAME_PATTERN_DESCRIPTION)
                )
                continue

            try:
                system_role = self._parse_system_role(row.get("system_role"))

                existing_user = UserDocument.find_one({"username": username}).run()
                if existing_user:
                    results.append(
                        self._bulk_result(
                            index,
                            row,
                            "skipped",
                            "user already exists",
                            system_role=existing_user.system_role,
                        )
                    )
                    continue

                initial_password = generate_temporary_password()
                user = UserDocument(
                    user_id=generate_user_id(),
                    username=username,
                    display_name=row.get("display_name") or None,
                    organization=row.get("organization") or None,
                    hashed_password=get_password_hash(initial_password),
                    access_token=secrets.token_urlsafe(32),
                    disabled=False,
                    system_role=system_role,
                    must_change_password=True,
                    system_info=SystemInfoModel(),
                )
                user.insert()

                results.append(
                    self._bulk_result(
                        index,
                        row,
                        "created",
                        initial_password=initial_password,
                        system_role=system_role,
                    )
                )
            except Exception as exc:
                logger.warning("Failed to import user from row %s: %s", index, exc)
                results.append(self._bulk_result(index, row, "failed", str(exc)))

        created = sum(1 for result in results if result.status == "created")
        skipped = sum(1 for result in results if result.status == "skipped")
        failed = sum(1 for result in results if result.status == "failed")

        return BulkUserImportResponse(
            results=results,
            created=created,
            skipped=skipped,
            failed=failed,
            total=len(results),
        )

    def list_users(self, skip: int = 0, limit: int = 100) -> UserListResponse:
        """List all users with project mapping."""
        total = UserDocument.find_all().count()
        users = list(UserDocument.find_all().skip(skip).limit(limit).run())

        usernames = [u.username for u in users]
        projects = list(ProjectDocument.find({"owner_username": {"$in": usernames}}).run())
        owner_project_map = {p.owner_username: p.project_id for p in projects}

        user_list = []
        for u in users:
            project_id = u.default_project_id or owner_project_map.get(u.username)
            user_list.append(
                UserListItem(
                    user_id=u.user_id,
                    username=u.username,
                    display_name=u.display_name,
                    organization=u.organization,
                    avatar_key=u.avatar_key,
                    disabled=u.disabled,
                    system_role=u.system_role,
                    default_project_id=project_id,
                    must_change_password=u.must_change_password,
                )
            )

        return UserListResponse(users=user_list, total=total)

    def get_user_details(self, username: str) -> UserDetailResponse:
        """Get detailed information about a user."""
        user = UserDocument.find_one({"username": username}).run()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{username}' not found",
            )
        return self._user_to_detail(user)

    def update_user(
        self,
        username: str,
        admin_username: str,
        display_name: str | None = None,
        organization: str | None = None,
        avatar_key: str | None = None,
        disabled: bool | None = None,
        system_role: SystemRole | None = None,
    ) -> UserDetailResponse:
        """Update user settings with validation."""
        user = UserDocument.find_one({"username": username}).run()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{username}' not found",
            )

        # Prevent demoting the last admin
        if system_role is not None and system_role != user.system_role:
            if user.system_role == SystemRole.ADMIN:
                admin_count = UserDocument.find({"system_role": SystemRole.ADMIN}).count()
                if admin_count <= 1:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot demote the last admin user",
                    )

        # Prevent admin from changing their own role
        if system_role is not None and username == admin_username:
            if system_role != user.system_role:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot change your own system role",
                )

        if display_name is not None:
            user.display_name = display_name
        if organization is not None:
            user.organization = organization
        if avatar_key is not None:
            user.avatar_key = avatar_key.strip() or None
        if disabled is not None:
            user.disabled = disabled
        if system_role is not None:
            user.system_role = system_role

        if user.system_info:
            user.system_info.updated_at = now()

        user.save()
        return self._user_to_detail(user)

    def delete_user(self, username: str, admin_username: str) -> dict[str, str]:
        """Delete a user with safety checks."""
        if username == admin_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account",
            )

        user = UserDocument.find_one({"username": username}).run()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{username}' not found",
            )

        if user.system_role == SystemRole.ADMIN:
            admin_count = UserDocument.find({"system_role": SystemRole.ADMIN}).count()
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete the last admin user",
                )

        user.delete()
        return {"message": f"User '{username}' deleted successfully"}

    # --- Project Management ---

    def list_projects(self, skip: int = 0, limit: int = 100) -> ProjectListResponse:
        """List all projects with member counts."""
        total = ProjectDocument.find_all().count()
        projects = list(ProjectDocument.find_all().skip(skip).limit(limit).run())

        project_list = []
        for p in projects:
            member_count = ProjectMembershipDocument.find({"project_id": p.project_id}).count()
            project_list.append(
                ProjectListItem(
                    project_id=p.project_id,
                    name=p.name,
                    owner_user_id=p.owner_user_id,
                    owner_username=p.owner_username,
                    description=p.description,
                    member_count=member_count,
                    created_at=p.system_info.created_at if p.system_info else None,
                )
            )

        return ProjectListResponse(projects=project_list, total=total)

    def delete_project(self, project_id: str, admin_username: str) -> dict[str, str]:
        """Delete a project with cascade cleanup."""
        project = ProjectDocument.find_one({"project_id": project_id}).run()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        admin_user_id = self._user_id_for_username(admin_username)
        if admin_user_id and project.owner_user_id == admin_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own project",
            )

        ProjectMembershipDocument.find({"project_id": project_id}).delete().run()
        UserDocument.find({"default_project_id": project_id}).update_many(
            {"$set": {"default_project_id": None}}
        ).run()
        project.delete()

        logger.info(f"Deleted project {project_id} ({project.name})")
        return {"message": f"Project '{project.name}' deleted successfully"}

    # --- Member Management ---

    def list_project_members(self, project_id: str) -> MemberListResponse:
        """List active members of a project."""
        project = ProjectDocument.find_one({"project_id": project_id}).run()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        memberships = list(
            ProjectMembershipDocument.find({"project_id": project_id, "status": "active"}).run()
        )

        members = []
        for m in memberships:
            user = UserDocument.find_one({"username": m.username}).run()
            members.append(
                MemberItem(
                    user_id=m.user_id,
                    username=m.username,
                    display_name=user.display_name if user else None,
                    organization=user.organization if user else None,
                    avatar_key=user.avatar_key if user else None,
                    role=m.role,
                    status=m.status,
                )
            )

        return MemberListResponse(members=members, total=len(members))

    def add_project_member(
        self, project_id: str, username: str, role: ProjectRole, admin_username: str
    ) -> MemberItem:
        """Add a member to a project."""
        project = ProjectDocument.find_one({"project_id": project_id}).run()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        user = UserDocument.find_one({"username": username}).run()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{username}' not found",
            )

        existing = ProjectMembershipDocument.find_one(
            {"project_id": project_id, "user_id": user.user_id}
        ).run()

        if existing:
            if existing.status == "active":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User '{username}' is already a member",
                )
            existing.role = role
            existing.status = "active"
            existing.user_id = user.user_id
            existing.invited_by = admin_username
            existing.invited_by_user_id = self._user_id_for_username(admin_username)
            existing.system_info.update_time()
            existing.save()
            logger.info("Reactivated %s in project %s as %s", username, project_id, role.value)
            return MemberItem(
                user_id=existing.user_id,
                username=existing.username,
                display_name=user.display_name,
                organization=user.organization,
                avatar_key=user.avatar_key,
                role=existing.role,
                status=existing.status,
            )

        membership = ProjectMembershipDocument(
            project_id=project_id,
            user_id=user.user_id,
            username=username,
            role=role,
            status="active",
            invited_by_user_id=self._user_id_for_username(admin_username),
            invited_by=admin_username,
            system_info=SystemInfoModel(),
        )
        membership.insert()

        logger.info("Added %s to project %s as %s", username, project_id, role.value)
        return MemberItem(
            user_id=membership.user_id,
            username=membership.username,
            display_name=user.display_name,
            organization=user.organization,
            avatar_key=user.avatar_key,
            role=membership.role,
            status=membership.status,
        )

    def remove_project_member(self, project_id: str, username: str) -> dict[str, str]:
        """Remove a member from a project."""
        project = ProjectDocument.find_one({"project_id": project_id}).run()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        user = UserDocument.find_one({"username": username}).run()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{username}' not found",
            )

        if user.user_id == project.owner_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the project owner",
            )

        membership = ProjectMembershipDocument.find_one(
            {"project_id": project_id, "user_id": user.user_id, "status": "active"}
        ).run()

        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member '{username}' not found in project",
            )

        membership.status = "revoked"
        membership.system_info.update_time()
        membership.save()

        return {"message": f"Member '{username}' removed from project"}

    def create_project_for_user(self, username: str) -> UserDetailResponse:
        """Create a default project for a user."""
        from qdash.api.lib.project_service import ProjectService

        user = UserDocument.find_one({"username": username}).run()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{username}' not found",
            )

        existing_project = ProjectDocument.find_one({"owner_user_id": user.user_id}).run()
        if existing_project:
            user.default_project_id = existing_project.project_id
            if user.system_info:
                user.system_info.updated_at = now()
            user.save()
            logger.info(f"Linked existing project to user {username}")
            return self._user_to_detail(user)

        if user.default_project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User '{username}' already has a project",
            )

        service = ProjectService()
        project = service.create_project(
            owner_username=username,
            name=f"{username}'s project",
        )

        user.default_project_id = project.project_id
        if user.system_info:
            user.system_info.updated_at = now()
        user.save()

        return self._user_to_detail(user)
