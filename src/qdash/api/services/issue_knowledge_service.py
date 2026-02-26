"""Service for issue-derived knowledge case management."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qdash.api.services.issue_service import IssueService

from qdash.api.schemas.issue_knowledge import (
    IssueKnowledgeResponse,
    ListIssueKnowledgeResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.dbmodel.issue_knowledge import IssueKnowledgeDocument
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AI draft generation prompt
# ---------------------------------------------------------------------------

_EXTRACT_KNOWLEDGE_PROMPT = """\
You are an expert in superconducting qubit calibration.
Analyze the following issue thread from a calibration task and extract a structured knowledge case.

Task name: {task_name}
Chip ID: {chip_id}
Qubit ID: {qid}

Issue title: {issue_title}
Issue thread:
{thread_text}

Extract a structured postmortem knowledge case in the following JSON format.
Be concise but precise. Use English for all fields.

{{
  "title": "Short descriptive title of the case",
  "severity": "critical | warning | info",
  "symptom": "What was observed (1-3 sentences)",
  "root_cause": "Why it happened (1-3 sentences)",
  "resolution": "How it was resolved (1-3 sentences)",
  "lesson_learned": ["Key takeaway 1", "Key takeaway 2"]
}}

Respond with ONLY the JSON object, no other text.
"""


class IssueKnowledgeService:
    """Service for issue knowledge CRUD and AI draft generation."""

    @staticmethod
    def _to_response(doc: IssueKnowledgeDocument) -> IssueKnowledgeResponse:
        return IssueKnowledgeResponse(
            id=str(doc.id),
            issue_id=doc.issue_id,
            task_id=doc.task_id,
            task_name=doc.task_name,
            status=doc.status,
            title=doc.title,
            date=doc.date,
            severity=doc.severity,
            chip_id=doc.chip_id,
            qid=doc.qid,
            resolution_status=doc.resolution_status,
            symptom=doc.symptom,
            root_cause=doc.root_cause,
            resolution=doc.resolution,
            lesson_learned=doc.lesson_learned,
            figure_paths=doc.figure_paths,
            thread_image_urls=doc.thread_image_urls,
            reviewed_by=doc.reviewed_by,
            pr_url=doc.pr_url,
            created_at=doc.system_info.created_at,
            updated_at=doc.system_info.updated_at,
        )

    # ----- AI draft generation -----

    @staticmethod
    def _build_thread_text(
        root_content: str,
        replies: list[dict[str, Any]],
    ) -> str:
        """Format issue thread as plain text for the LLM prompt."""
        parts = [f"[Original] {root_content}"]
        for reply in replies:
            role = "AI" if reply.get("is_ai") else "User"
            parts.append(f"[{role}] {reply['content']}")
        return "\n\n".join(parts)

    async def generate_draft(
        self,
        project_id: str,
        issue_id: str,
        issue_service: IssueService,
    ) -> IssueKnowledgeResponse:
        """Generate an AI knowledge draft from a closed issue thread.

        Parameters
        ----------
        project_id : str
            Project identifier.
        issue_id : str
            Root issue ID.
        issue_service : IssueService
            Issue service instance for fetching thread data.

        Returns
        -------
        IssueKnowledgeResponse
            The created draft knowledge case.

        """
        # Delete any existing draft or rejected case (allows regeneration)
        existing = IssueKnowledgeDocument.find_one(
            {
                "project_id": project_id,
                "issue_id": issue_id,
                "status": {"$in": ["draft", "rejected"]},
            }
        ).run()
        if existing is not None:
            existing.delete()
            logger.info(
                "Deleted existing %s for issue %s (regenerating)", existing.status, issue_id
            )

        # Prevent regeneration if already approved
        approved = IssueKnowledgeDocument.find_one(
            {"project_id": project_id, "issue_id": issue_id, "status": "approved"}
        ).run()
        if approved is not None:
            raise HTTPException(
                status_code=409,
                detail="An approved knowledge case already exists for this issue",
            )

        # Build context from issue thread
        ai_context = issue_service.build_ai_reply_context(
            project_id=project_id,
            issue_id=issue_id,
        )
        if ai_context["root_doc"] is None:
            raise HTTPException(status_code=404, detail="Issue not found")

        root_doc = ai_context["root_doc"]
        chip_id = ai_context.get("chip_id") or ""
        qid = ai_context.get("qid") or ""
        task_id = ai_context["task_id"]

        # Resolve task_name from task_result_history
        # Use ``name`` (e.g. "CheckT1") not ``task_type`` (e.g. "qubit")
        # so it matches the knowledge repo directory structure.
        task_name = ""
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        task_result = TaskResultHistoryDocument.find_one({"task_id": task_id}).run()
        figure_paths: list[str] = []
        if task_result:
            task_name = task_result.name or ""
            figure_paths = task_result.figure_path or []

        # Build thread text
        replies = []
        reply_docs = issue_service.get_issue_replies(
            project_id=project_id,
            issue_id=issue_id,
        )
        for r in reply_docs:
            replies.append({"content": r.content, "is_ai": r.is_ai_reply})

        thread_text = self._build_thread_text(root_doc.content, replies)

        # Extract image URLs from issue thread content
        thread_image_urls: list[str] = []
        img_pattern = re.compile(r"!\[.*?\]\((.*?)\)")
        all_content = [root_doc.content] + [r.content for r in reply_docs]
        for content in all_content:
            for url in img_pattern.findall(content):
                if url not in thread_image_urls:
                    thread_image_urls.append(url)

        # Call LLM to extract knowledge
        extracted = await self._call_llm_extract(
            task_name=task_name,
            chip_id=chip_id,
            qid=qid,
            issue_title=root_doc.title or "",
            thread_text=thread_text,
        )

        if not extracted:
            raise HTTPException(
                status_code=502,
                detail="Failed to extract knowledge from issue thread. Check copilot configuration.",
            )

        # Validate and sanitise LLM output
        validated = self._validate_extracted(extracted)

        # Save as draft
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        doc = IssueKnowledgeDocument(
            project_id=project_id,
            issue_id=issue_id,
            task_id=task_id,
            task_name=task_name,
            status="draft",
            title=validated.get("title", root_doc.title or "Untitled"),
            date=today,
            severity=validated.get("severity", "warning"),
            chip_id=chip_id,
            qid=qid,
            resolution_status="resolved",
            symptom=validated.get("symptom", ""),
            root_cause=validated.get("root_cause", ""),
            resolution=validated.get("resolution", ""),
            lesson_learned=validated.get("lesson_learned", []),
            figure_paths=figure_paths,
            thread_image_urls=thread_image_urls,
        )
        doc.insert()

        logger.info("Generated knowledge draft for issue %s (task=%s)", issue_id, task_name)
        return self._to_response(doc)

    _VALID_SEVERITIES = {"critical", "warning", "info"}

    @classmethod
    def _validate_extracted(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Validate and sanitise the LLM-extracted knowledge dict.

        Ensures types are correct and values are within expected ranges.
        """
        validated: dict[str, Any] = {}

        # title – required string, truncate to 200 chars
        title = data.get("title")
        if isinstance(title, str) and title.strip():
            validated["title"] = title.strip()[:200]

        # severity – must be one of the allowed values
        severity = data.get("severity")
        if isinstance(severity, str) and severity in cls._VALID_SEVERITIES:
            validated["severity"] = severity
        else:
            validated["severity"] = "warning"

        # Free-text fields – truncate to 5000 chars
        for key in ("symptom", "root_cause", "resolution"):
            val = data.get(key)
            if isinstance(val, str):
                validated[key] = val.strip()[:5000]

        # lesson_learned – list of strings, max 50 items, each max 2000 chars
        lessons = data.get("lesson_learned")
        if isinstance(lessons, list):
            validated["lesson_learned"] = [
                str(item).strip()[:2000] for item in lessons[:50] if isinstance(item, str)
            ]

        return validated

    @staticmethod
    async def _call_llm_extract(
        task_name: str,
        chip_id: str,
        qid: str,
        issue_title: str,
        thread_text: str,
    ) -> dict[str, Any]:
        """Call LLM to extract structured knowledge from issue thread."""
        from qdash.api.lib.copilot_config import load_copilot_config

        config = load_copilot_config()
        if not config.enabled:
            logger.warning("Copilot disabled, returning empty extraction")
            return {}

        prompt = _EXTRACT_KNOWLEDGE_PROMPT.format(
            task_name=task_name,
            chip_id=chip_id,
            qid=qid,
            issue_title=issue_title,
            thread_text=thread_text,
        )

        try:
            from qdash.api.lib.copilot_agent import _build_client

            client = _build_client(config)
            response = await client.chat.completions.create(
                model=config.model.name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1000,
            )
            raw = response.choices[0].message.content or ""
            # Strip markdown code fences if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[: raw.rfind("```")]
            result: dict[str, Any] = json.loads(raw.strip())
            if not isinstance(result, dict):
                logger.warning("LLM returned non-dict JSON: %s", type(result).__name__)
                return {}
            return result
        except json.JSONDecodeError:
            logger.exception("LLM returned invalid JSON")
            return {}
        except Exception:
            logger.exception("LLM knowledge extraction failed")
            return {}

    # ----- CRUD -----

    def list_knowledge(
        self,
        project_id: str,
        skip: int = 0,
        limit: int = 50,
        status: str | None = None,
        task_name: str | None = None,
    ) -> ListIssueKnowledgeResponse:
        """List knowledge cases with optional filters."""
        query: dict[str, object] = {"project_id": project_id}
        if status:
            query["status"] = status
        if task_name:
            query["task_name"] = task_name

        total = IssueKnowledgeDocument.find(query).count()
        docs = (
            IssueKnowledgeDocument.find(query)
            .sort("-system_info.created_at")
            .skip(skip)
            .limit(limit)
            .to_list()
        )
        return ListIssueKnowledgeResponse(
            items=[self._to_response(d) for d in docs],
            total=total,
            skip=skip,
            limit=limit,
        )

    def get_knowledge(self, project_id: str, knowledge_id: str) -> IssueKnowledgeResponse:
        """Get a single knowledge case."""
        from bson import ObjectId

        doc = IssueKnowledgeDocument.find_one(
            {"_id": ObjectId(knowledge_id), "project_id": project_id}
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Knowledge case not found")
        return self._to_response(doc)

    def update_knowledge(
        self,
        project_id: str,
        knowledge_id: str,
        title: str | None = None,
        severity: str | None = None,
        symptom: str | None = None,
        root_cause: str | None = None,
        resolution: str | None = None,
        lesson_learned: list[str] | None = None,
    ) -> IssueKnowledgeResponse:
        """Update a knowledge draft's content."""
        from bson import ObjectId

        doc = IssueKnowledgeDocument.find_one(
            {"_id": ObjectId(knowledge_id), "project_id": project_id}
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Knowledge case not found")
        if doc.status != "draft":
            raise HTTPException(status_code=400, detail="Only drafts can be edited")

        if title is not None:
            doc.title = title
        if severity is not None:
            doc.severity = severity
        if symptom is not None:
            doc.symptom = symptom
        if root_cause is not None:
            doc.root_cause = root_cause
        if resolution is not None:
            doc.resolution = resolution
        if lesson_learned is not None:
            doc.lesson_learned = lesson_learned

        doc.system_info.update_time()
        doc.save()
        return self._to_response(doc)

    # ----- Markdown generation helpers -----

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert a title to a filename-safe slug."""
        slug = text.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        return slug[:80].strip("-")

    @staticmethod
    def _doc_to_markdown(doc: IssueKnowledgeDocument) -> str:
        """Convert a knowledge document to case Markdown content.

        Figure paths are rewritten to ``./figures/<filename>`` so that
        they resolve correctly when the images are committed alongside
        the case Markdown file in the knowledge repository.
        """
        lines = [f"# {doc.title}", ""]

        meta = []
        if doc.date:
            meta.append(f"- date: {doc.date}")
        if doc.severity:
            meta.append(f"- severity: {doc.severity}")
        if doc.chip_id:
            meta.append(f"- chip_id: {doc.chip_id}")
        if doc.qid:
            meta.append(f"- qid: {doc.qid}")
        if doc.resolution_status:
            meta.append(f"- status: {doc.resolution_status}")
        if doc.issue_id:
            meta.append(f"- issue_id: {doc.issue_id}")
        if meta:
            lines.extend(meta)
            lines.append("")

        if doc.symptom:
            lines.extend(["## Symptom", "", doc.symptom, ""])
        if doc.root_cause:
            lines.extend(["## Root cause", "", doc.root_cause, ""])
        if doc.resolution:
            lines.extend(["## Resolution", "", doc.resolution, ""])
        if doc.lesson_learned:
            lines.append("## Lesson learned")
            lines.append("")
            for lesson in doc.lesson_learned:
                lines.append(f"- {lesson}")
            lines.append("")

        if doc.figure_paths:
            lines.append("## Figures")
            lines.append("")
            for i, fig_path in enumerate(doc.figure_paths, 1):
                filename = Path(fig_path).name
                lines.append(f"![Figure {i}](./figures/{filename})")
            lines.append("")

        if doc.thread_image_urls:
            lines.append("## Thread images")
            lines.append("")
            for i, url in enumerate(doc.thread_image_urls, 1):
                lines.append(f"![Thread image {i}]({url})")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _find_task_category_dir(repo_dir: Path, task_name: str) -> Path | None:
        """Find the category directory for a task in the knowledge repo."""
        for category_dir in repo_dir.iterdir():
            if not category_dir.is_dir() or category_dir.name.startswith("."):
                continue
            task_dir = category_dir / task_name
            if task_dir.is_dir():
                return category_dir
        return None

    # ----- GitHub PR creation -----

    @staticmethod
    def _create_knowledge_pr(
        doc: IssueKnowledgeDocument,
        md_content: str,
        repo_subpath: str,
    ) -> str | None:
        """Create a PR on the knowledge repo with the case markdown.

        Returns the PR URL or None if knowledge repo is not configured.
        """
        from urllib.parse import urlparse, urlunparse

        import httpx
        from git import Repo

        repo_url = os.getenv("KNOWLEDGE_REPO_URL")
        github_user = os.getenv("GITHUB_USER")
        github_token = os.getenv("GITHUB_TOKEN")

        if not all([repo_url, github_user, github_token]):
            logger.info("KNOWLEDGE_REPO_URL not configured, skipping PR creation")
            return None

        assert repo_url is not None

        # Parse owner/repo from URL
        match = re.match(r"https?://[^/]+/([^/]+)/([^/]+?)(?:\.git)?$", repo_url)
        if not match:
            logger.error("Invalid KNOWLEDGE_REPO_URL format: %s", repo_url)
            return None
        owner = match.group(1)
        repo_name = match.group(2)

        parsed = urlparse(repo_url)
        auth_netloc = f"{github_user}:{github_token}@{parsed.netloc}"
        auth_url: str = urlunparse((parsed.scheme, auth_netloc, parsed.path, "", "", ""))

        temp_dir = tempfile.mkdtemp()
        try:
            repo = Repo.clone_from(auth_url, temp_dir, branch="main", depth=1)

            branch_name = (
                f"knowledge/{doc.task_name or 'unknown'}"
                f"/{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}"
            )
            repo.git.checkout("-b", branch_name)

            # Write the case file
            target = Path(temp_dir) / repo_subpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(md_content, encoding="utf-8")

            files_to_add = [repo_subpath]

            # Copy figure images alongside the case markdown
            if doc.figure_paths:
                figures_dir = target.parent / "figures"
                figures_dir.mkdir(parents=True, exist_ok=True)
                for fig_path in doc.figure_paths:
                    src = Path(fig_path)
                    if src.is_file():
                        dst = figures_dir / src.name
                        shutil.copy2(src, dst)
                        rel = str(dst.relative_to(Path(temp_dir)))
                        files_to_add.append(rel)
                    else:
                        logger.warning("Figure not found, skipping: %s", fig_path)

            repo.index.add(files_to_add)
            diff = repo.index.diff("HEAD")
            if not diff:
                logger.info("No changes to commit for knowledge PR")
                return None

            repo.git.config("user.name", "github-actions[bot]")
            repo.git.config("user.email", "github-actions[bot]@users.noreply.github.com")

            from qdash.common.datetime_utils import now_iso

            commit_msg = f"Add case: {doc.title}"
            repo.index.commit(f"{commit_msg} at {now_iso()}")
            repo.remotes.origin.push(refspec=f"{branch_name}:{branch_name}")

            # Create PR
            pr_body = (
                f"## New Knowledge Case\n\n"
                f"- **Task**: {doc.task_name}\n"
                f"- **Title**: {doc.title}\n"
                f"- **Severity**: {doc.severity}\n"
                f"- **Chip**: {doc.chip_id or 'N/A'} / **Qubit**: {doc.qid or 'N/A'}\n"
                f"- **Source Issue**: {doc.issue_id}\n"
                f"- **Approved by**: {doc.reviewed_by}\n"
            )

            pr_response = httpx.post(
                f"https://api.github.com/repos/{owner}/{repo_name}/pulls",
                headers={
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={
                    "title": commit_msg,
                    "head": branch_name,
                    "base": "main",
                    "body": pr_body,
                },
                timeout=30,
            )
            pr_response.raise_for_status()
            pr_data = pr_response.json()
            pr_url: str = pr_data["html_url"]
            logger.info("Knowledge PR created: %s", pr_url)
            return pr_url

        except Exception:
            logger.exception("Failed to create knowledge PR")
            return None
        finally:
            if Path(temp_dir).exists():
                shutil.rmtree(temp_dir)

    def approve_knowledge(
        self,
        project_id: str,
        knowledge_id: str,
        username: str,
    ) -> IssueKnowledgeResponse:
        """Approve a knowledge draft and create a PR on the knowledge repo."""
        from bson import ObjectId

        doc = IssueKnowledgeDocument.find_one(
            {"_id": ObjectId(knowledge_id), "project_id": project_id}
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Knowledge case not found")
        if doc.status != "draft":
            raise HTTPException(status_code=400, detail="Only drafts can be approved")

        doc.status = "approved"
        doc.reviewed_by = username

        # Generate markdown and create PR
        md_content = self._doc_to_markdown(doc)
        slug = self._slugify(doc.title)
        date_prefix = doc.date or "unknown"
        filename = f"{date_prefix}_{slug}.md"

        # Determine repo subpath by looking up the task in the knowledge repo
        repo_url = os.getenv("KNOWLEDGE_REPO_URL")
        if repo_url:
            from qdash.datamodel.task_knowledge import get_task_category_dir

            cat_dir = get_task_category_dir(doc.task_name)
            repo_subpath = f"{cat_dir}/{doc.task_name}/cases/{filename}"

            pr_url = self._create_knowledge_pr(doc, md_content, repo_subpath)
            doc.pr_url = pr_url

        doc.system_info.update_time()
        doc.save()

        logger.info("Knowledge %s approved by %s", knowledge_id, username)
        return self._to_response(doc)

    def reject_knowledge(
        self,
        project_id: str,
        knowledge_id: str,
        username: str,
    ) -> IssueKnowledgeResponse:
        """Reject a knowledge draft."""
        from bson import ObjectId

        doc = IssueKnowledgeDocument.find_one(
            {"_id": ObjectId(knowledge_id), "project_id": project_id}
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Knowledge case not found")
        if doc.status != "draft":
            raise HTTPException(status_code=400, detail="Only drafts can be rejected")

        doc.status = "rejected"
        doc.reviewed_by = username
        doc.system_info.update_time()
        doc.save()

        logger.info("Knowledge %s rejected by %s", knowledge_id, username)
        return self._to_response(doc)

    def delete_knowledge(
        self,
        project_id: str,
        knowledge_id: str,
    ) -> SuccessResponse:
        """Delete a knowledge case."""
        from bson import ObjectId

        doc = IssueKnowledgeDocument.find_one(
            {"_id": ObjectId(knowledge_id), "project_id": project_id}
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Knowledge case not found")

        doc.delete()
        return SuccessResponse(message="Knowledge case deleted")
