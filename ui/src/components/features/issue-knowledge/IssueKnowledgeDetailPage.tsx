"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  XCircle,
  Pencil,
  Save,
  X,
  ExternalLink,
  GitPullRequest,
  Image,
} from "lucide-react";
import { PageContainer } from "@/components/ui/PageContainer";
import { useIssueKnowledgeDetail } from "@/hooks/useIssueKnowledge";
import { formatDateTime } from "@/lib/utils/datetime";

function SeverityBadge({ severity }: { severity?: string }) {
  const color =
    severity === "critical"
      ? "badge-error"
      : severity === "warning"
        ? "badge-warning"
        : "badge-info";
  return (
    <span className={`badge badge-sm ${color}`}>{severity ?? "info"}</span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "approved"
      ? "badge-success"
      : status === "rejected"
        ? "badge-error"
        : "badge-ghost";
  return <span className={`badge badge-sm ${color}`}>{status}</span>;
}

function EditableField({
  label,
  value,
  isEditing,
  onChange,
  multiline = false,
}: {
  label: string;
  value: string;
  isEditing: boolean;
  onChange: (value: string) => void;
  multiline?: boolean;
}) {
  if (isEditing) {
    return (
      <div>
        <label className="text-xs font-semibold text-base-content/60 mb-1 block">
          {label}
        </label>
        {multiline ? (
          <textarea
            className="textarea textarea-bordered w-full text-sm"
            rows={3}
            value={value}
            onChange={(e) => onChange(e.target.value)}
          />
        ) : (
          <input
            type="text"
            className="input input-bordered input-sm w-full"
            value={value}
            onChange={(e) => onChange(e.target.value)}
          />
        )}
      </div>
    );
  }

  return (
    <div>
      <label className="text-xs font-semibold text-base-content/60 mb-1 block">
        {label}
      </label>
      <p className="text-sm text-base-content/80 whitespace-pre-wrap">
        {value || <span className="italic text-base-content/30">Empty</span>}
      </p>
    </div>
  );
}

export function IssueKnowledgeDetailPage({
  knowledgeId,
}: {
  knowledgeId: string;
}) {
  const router = useRouter();
  const { knowledge, isLoading, isUpdating, update, approve, reject } =
    useIssueKnowledgeDetail(knowledgeId);

  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editSeverity, setEditSeverity] = useState("");
  const [editSymptom, setEditSymptom] = useState("");
  const [editRootCause, setEditRootCause] = useState("");
  const [editResolution, setEditResolution] = useState("");
  const [editLessons, setEditLessons] = useState("");

  useEffect(() => {
    if (knowledge) {
      setEditTitle(knowledge.title);
      setEditSeverity(knowledge.severity ?? "warning");
      setEditSymptom(knowledge.symptom ?? "");
      setEditRootCause(knowledge.root_cause ?? "");
      setEditResolution(knowledge.resolution ?? "");
      setEditLessons((knowledge.lesson_learned ?? []).join("\n"));
    }
  }, [knowledge]);

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (!knowledge) {
    return (
      <div className="text-center py-16 text-base-content/50">
        Knowledge case not found.
      </div>
    );
  }

  const isDraft = knowledge.status === "draft";

  const handleSave = async () => {
    await update({
      title: editTitle,
      severity: editSeverity,
      symptom: editSymptom,
      root_cause: editRootCause,
      resolution: editResolution,
      lesson_learned: editLessons
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean),
    });
    setIsEditing(false);
  };

  const handleApprove = async () => {
    await approve();
    router.push("/issue-knowledge");
  };

  const handleReject = async () => {
    await reject();
    router.push("/issue-knowledge");
  };

  return (
    <PageContainer maxWidth>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => router.push("/issue-knowledge")}
          className="btn btn-ghost btn-sm btn-circle"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-lg font-bold">
              {isEditing ? (
                <input
                  type="text"
                  className="input input-bordered input-sm font-bold"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                />
              ) : (
                knowledge.title
              )}
            </h1>
            <StatusBadge status={knowledge.status} />
            <SeverityBadge
              severity={isEditing ? editSeverity : knowledge.severity}
            />
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-base-content/50">
            <span className="font-mono text-primary">
              {knowledge.task_name}
            </span>
            {knowledge.chip_id && <span>{knowledge.chip_id}</span>}
            {knowledge.qid && <span>{knowledge.qid}</span>}
            <span>{knowledge.date}</span>
          </div>
        </div>
      </div>

      {/* Links */}
      <div className="flex items-center gap-3 mb-4 text-xs">
        <Link
          href={`/issues/${knowledge.issue_id}`}
          className="flex items-center gap-1 text-primary hover:underline"
        >
          <ExternalLink className="h-3 w-3" />
          Source Issue
        </Link>
        <Link
          href={`/task-results/${knowledge.task_id}`}
          className="flex items-center gap-1 text-primary hover:underline"
        >
          <ExternalLink className="h-3 w-3" />
          Task Result
        </Link>
        <span className="text-base-content/40">
          Created {formatDateTime(knowledge.created_at)}
        </span>
        {knowledge.reviewed_by && (
          <span className="text-base-content/40">
            Reviewed by {String(knowledge.reviewed_by)}
          </span>
        )}
        {knowledge.pr_url && (
          <a
            href={String(knowledge.pr_url)}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-success hover:underline"
          >
            <GitPullRequest className="h-3 w-3" />
            Pull Request
          </a>
        )}
      </div>

      {/* Action buttons */}
      {isDraft && (
        <div className="flex items-center gap-2 mb-6">
          {isEditing ? (
            <>
              <button
                onClick={handleSave}
                disabled={isUpdating}
                className="btn btn-primary btn-sm gap-1"
              >
                {isUpdating ? (
                  <span className="loading loading-spinner loading-xs"></span>
                ) : (
                  <Save className="h-3 w-3" />
                )}
                Save
              </button>
              <button
                onClick={() => setIsEditing(false)}
                className="btn btn-ghost btn-sm gap-1"
              >
                <X className="h-3 w-3" />
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setIsEditing(true)}
                className="btn btn-ghost btn-sm gap-1"
              >
                <Pencil className="h-3 w-3" />
                Edit
              </button>
              <button
                onClick={handleApprove}
                className="btn btn-success btn-sm gap-1"
              >
                <GitPullRequest className="h-3 w-3" />
                Create PR
              </button>
              <button
                onClick={handleReject}
                className="btn btn-ghost btn-sm gap-1"
              >
                <XCircle className="h-3 w-3" />
                Reject
              </button>
            </>
          )}
        </div>
      )}

      {/* Severity selector (editing mode) */}
      {isEditing && (
        <div className="mb-4">
          <label className="text-xs font-semibold text-base-content/60 mb-1 block">
            Severity
          </label>
          <select
            className="select select-bordered select-sm"
            value={editSeverity}
            onChange={(e) => setEditSeverity(e.target.value)}
          >
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </select>
        </div>
      )}

      {/* Content sections */}
      <div className="space-y-6">
        <div className="bg-base-200/50 rounded-lg p-4">
          <EditableField
            label="Symptom"
            value={isEditing ? editSymptom : (knowledge.symptom ?? "")}
            isEditing={isEditing}
            onChange={setEditSymptom}
            multiline
          />
        </div>

        <div className="bg-base-200/50 rounded-lg p-4">
          <EditableField
            label="Root Cause"
            value={isEditing ? editRootCause : (knowledge.root_cause ?? "")}
            isEditing={isEditing}
            onChange={setEditRootCause}
            multiline
          />
        </div>

        <div className="bg-base-200/50 rounded-lg p-4">
          <EditableField
            label="Resolution"
            value={isEditing ? editResolution : (knowledge.resolution ?? "")}
            isEditing={isEditing}
            onChange={setEditResolution}
            multiline
          />
        </div>

        <div className="bg-base-200/50 rounded-lg p-4">
          {isEditing ? (
            <div>
              <label className="text-xs font-semibold text-base-content/60 mb-1 block">
                Lessons Learned (one per line)
              </label>
              <textarea
                className="textarea textarea-bordered w-full text-sm"
                rows={4}
                value={editLessons}
                onChange={(e) => setEditLessons(e.target.value)}
              />
            </div>
          ) : (
            <div>
              <label className="text-xs font-semibold text-base-content/60 mb-1 block">
                Lessons Learned
              </label>
              {knowledge.lesson_learned &&
              knowledge.lesson_learned.length > 0 ? (
                <ul className="list-disc list-inside space-y-1">
                  {knowledge.lesson_learned.map((lesson, i) => (
                    <li key={i} className="text-sm text-base-content/80">
                      {lesson}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm italic text-base-content/30">
                  No lessons recorded
                </p>
              )}
            </div>
          )}
        </div>

        {/* Images section */}
        {((knowledge.figure_paths && knowledge.figure_paths.length > 0) ||
          (knowledge.thread_image_urls &&
            knowledge.thread_image_urls.length > 0)) && (
          <div className="bg-base-200/50 rounded-lg p-4">
            <label className="text-xs font-semibold text-base-content/60 mb-3 block flex items-center gap-1">
              <Image className="h-3 w-3" />
              Images
            </label>

            {knowledge.figure_paths && knowledge.figure_paths.length > 0 && (
              <div className="mb-4">
                <p className="text-xs text-base-content/50 mb-2">
                  Task Result Figures
                </p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {knowledge.figure_paths.map((path, i) => (
                    <a
                      key={i}
                      href={`/api/executions/figure?path=${encodeURIComponent(path)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block border border-base-300 rounded overflow-hidden hover:border-primary transition-colors"
                    >
                      <img
                        src={`/api/executions/figure?path=${encodeURIComponent(path)}`}
                        alt={`Figure ${i + 1}`}
                        className="w-full h-auto"
                      />
                    </a>
                  ))}
                </div>
              </div>
            )}

            {knowledge.thread_image_urls &&
              knowledge.thread_image_urls.length > 0 && (
                <div>
                  <p className="text-xs text-base-content/50 mb-2">
                    Thread Images
                  </p>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {knowledge.thread_image_urls.map((url, i) => (
                      <a
                        key={i}
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block border border-base-300 rounded overflow-hidden hover:border-primary transition-colors"
                      >
                        <img
                          src={url}
                          alt={`Thread image ${i + 1}`}
                          className="w-full h-auto"
                        />
                      </a>
                    ))}
                  </div>
                </div>
              )}
          </div>
        )}
      </div>
    </PageContainer>
  );
}
