"use client";

import type { ProjectListItem } from "@/schemas";

import { formatDate } from "@/lib/utils/datetime";

type AdminProjectsPanelProps = {
  projects: ProjectListItem[];
  currentUsername?: string;
  onManageMembers: (project: ProjectListItem) => void;
  onDeleteProject: (project: ProjectListItem) => void;
};

export function AdminProjectsPanel({
  projects,
  currentUsername,
  onManageMembers,
  onDeleteProject,
}: AdminProjectsPanelProps) {
  return (
    <div className="card bg-base-200 shadow-lg">
      <div className="card-body">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="card-title">Project Management</h2>
        </div>

        <div className="space-y-3 sm:hidden">
          {projects.map((project) => (
            <div key={project.project_id} className="card bg-base-100 shadow-sm">
              <div className="card-body p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-medium">{project.name}</h3>
                    {project.description && (
                      <p className="text-xs text-base-content/60">{project.description}</p>
                    )}
                  </div>
                  <span className="badge badge-ghost badge-sm">{project.member_count} members</span>
                </div>
                <div className="mt-1 text-sm text-base-content/60">
                  <span className="font-mono">{project.owner_username}</span>
                  {project.created_at && (
                    <span className="ml-2">· {formatDate(project.created_at)}</span>
                  )}
                </div>
                <div className="mt-2 flex justify-end gap-1 border-t border-base-300 pt-2">
                  <button className="btn btn-xs btn-ghost" onClick={() => onManageMembers(project)}>
                    Members
                  </button>
                  {project.owner_username === currentUsername ? (
                    <span
                      className="btn btn-xs btn-ghost btn-disabled opacity-50"
                      title="Cannot delete your own project"
                    >
                      Delete
                    </span>
                  ) : (
                    <button
                      className="btn btn-xs btn-error btn-ghost"
                      onClick={() => onDeleteProject(project)}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="hidden overflow-x-auto sm:block">
          <table className="table table-zebra">
            <thead>
              <tr>
                <th>Project Name</th>
                <th>Owner</th>
                <th>Members</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((project) => (
                <tr key={project.project_id}>
                  <td>
                    <div>
                      <div className="font-medium">{project.name}</div>
                      {project.description && (
                        <div className="text-xs text-base-content/60">{project.description}</div>
                      )}
                    </div>
                  </td>
                  <td className="font-mono">{project.owner_username}</td>
                  <td>
                    <span className="badge badge-ghost">{project.member_count}</span>
                  </td>
                  <td className="text-sm text-base-content/60">{formatDate(project.created_at)}</td>
                  <td>
                    <div className="flex gap-2">
                      <button
                        className="btn btn-sm btn-ghost"
                        onClick={() => onManageMembers(project)}
                      >
                        Members
                      </button>
                      {project.owner_username === currentUsername ? (
                        <span
                          className="btn btn-sm btn-ghost btn-disabled opacity-50"
                          title="Cannot delete your own project"
                        >
                          Delete
                        </span>
                      ) : (
                        <button
                          className="btn btn-sm btn-error btn-ghost"
                          onClick={() => onDeleteProject(project)}
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
