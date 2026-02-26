"""Service for issue-derived knowledge case management."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

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
            reviewed_by=doc.reviewed_by,
            created_at=doc.system_info.created_at,
            updated_at=doc.system_info.updated_at,
        )

    # ----- AI draft generation -----

    @staticmethod
    def _build_thread_text(
        root_content: str,
        replies: list[dict[str, str]],
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
        issue_service: Any,
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
        # Check if a draft already exists for this issue
        existing = IssueKnowledgeDocument.find_one(
            {"project_id": project_id, "issue_id": issue_id}
        ).run()
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="A knowledge draft already exists for this issue",
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
        task_name = ""
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        task_result = TaskResultHistoryDocument.find_one({"task_id": task_id}).run()
        if task_result:
            task_name = task_result.task_name or ""

        # Build thread text
        replies = []
        reply_docs = issue_service.get_issue_replies(
            project_id=project_id,
            issue_id=issue_id,
        )
        for r in reply_docs:
            replies.append({"content": r.content, "is_ai": r.is_ai_reply})

        thread_text = self._build_thread_text(root_doc.content, replies)

        # Call LLM to extract knowledge
        extracted = await self._call_llm_extract(
            task_name=task_name,
            chip_id=chip_id,
            qid=qid,
            issue_title=root_doc.title or "",
            thread_text=thread_text,
        )

        # Save as draft
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        doc = IssueKnowledgeDocument(
            project_id=project_id,
            issue_id=issue_id,
            task_id=task_id,
            task_name=task_name,
            status="draft",
            title=extracted.get("title", root_doc.title or "Untitled"),
            date=today,
            severity=extracted.get("severity", "warning"),
            chip_id=chip_id,
            qid=qid,
            resolution_status="resolved",
            symptom=extracted.get("symptom", ""),
            root_cause=extracted.get("root_cause", ""),
            resolution=extracted.get("resolution", ""),
            lesson_learned=extracted.get("lesson_learned", []),
        )
        doc.insert()

        logger.info(
            "Generated knowledge draft for issue %s (task=%s)", issue_id, task_name
        )
        return self._to_response(doc)

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
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url or None,
            )
            response = await client.chat.completions.create(
                model=config.model,
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
            return json.loads(raw.strip())
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

    def approve_knowledge(
        self,
        project_id: str,
        knowledge_id: str,
        username: str,
    ) -> IssueKnowledgeResponse:
        """Approve a knowledge draft."""
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
