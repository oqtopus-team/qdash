"""Admin service for user and project management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from qdash.api.schemas.admin import (
    MemberItem,
    MemberListResponse,
    ProjectListItem,
    ProjectListResponse,
    UserDetailResponse,
    UserListItem,
    UserListResponse,
)
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import SystemRole
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument

logger = logging.getLogger(__name__)


class AdminService:
    """Service for admin user and project management operations."""

    @staticmethod
    def _user_to_detail(user: UserDocument) -> UserDetailResponse:
        """Convert a UserDocument to UserDetailResponse."""
        return UserDetailResponse(
            username=user.username,
            full_name=user.full_name,
            disabled=user.disabled,
            system_role=user.system_role,
            default_project_id=user.default_project_id,
            created_at=user.system_info.created_at if user.system_info else None,
            updated_at=user.system_info.updated_at if user.system_info else None,
        )

    # --- User Management ---

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
                    username=u.username,
                    full_name=u.full_name,
                    disabled=u.disabled,
                    system_role=u.system_role,
                    default_project_id=project_id,
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
        full_name: str | None = None,
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

        if full_name is not None:
            user.full_name = full_name
        if disabled is not None:
            user.disabled = disabled
        if system_role is not None:
            user.system_role = system_role

        if user.system_info:
            user.system_info.updated_at = datetime.now(timezone.utc).isoformat()

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

        if project.owner_username == admin_username:
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
                    username=m.username,
                    full_name=user.full_name if user else None,
                    role=m.role,
                    status=m.status,
                )
            )

        return MemberListResponse(members=members, total=len(members))

    def add_project_member(self, project_id: str, username: str, admin_username: str) -> MemberItem:
        """Add a member to a project as viewer."""
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
            {"project_id": project_id, "username": username}
        ).run()

        if existing:
            if existing.status == "active":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User '{username}' is already a member",
                )
            existing.role = ProjectRole.VIEWER
            existing.status = "active"
            existing.invited_by = admin_username
            existing.system_info.update_time()
            existing.save()
            logger.info(f"Reactivated {username} in project {project_id} as viewer")
            return MemberItem(
                username=existing.username,
                full_name=user.full_name,
                role=existing.role,
                status=existing.status,
            )

        membership = ProjectMembershipDocument(
            project_id=project_id,
            username=username,
            role=ProjectRole.VIEWER,
            status="active",
            invited_by=admin_username,
            system_info=SystemInfoModel(),
        )
        membership.insert()

        logger.info(f"Added {username} to project {project_id} as viewer")
        return MemberItem(
            username=membership.username,
            full_name=user.full_name,
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

        if project.owner_username == username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the project owner",
            )

        membership = ProjectMembershipDocument.find_one(
            {"project_id": project_id, "username": username, "status": "active"}
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

        existing_project = ProjectDocument.find_one({"owner_username": username}).run()
        if existing_project:
            user.default_project_id = existing_project.project_id
            if user.system_info:
                user.system_info.updated_at = datetime.now(timezone.utc).isoformat()
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
            user.system_info.updated_at = datetime.now(timezone.utc).isoformat()
        user.save()

        return self._user_to_detail(user)
