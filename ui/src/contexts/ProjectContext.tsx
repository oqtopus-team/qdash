"use client";

import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useState, useEffect, useMemo } from "react";

import { useQueryClient } from "@tanstack/react-query";

import type { Query, QueryClient } from "@tanstack/react-query";
import { usePathname } from "next/navigation";

import { useAuth } from "./AuthContext";

import type { ProjectResponse, ProjectRole } from "@/schemas";

import { useListProjects, useListProjectMembers } from "@/client/projects/projects";

interface ProjectContextType {
  currentProject: ProjectResponse | null;
  projects: ProjectResponse[];
  projectId: string | null;
  role: ProjectRole | null;
  isOwner: boolean;
  isEditor: boolean;
  isViewer: boolean;
  canEdit: boolean;
  can: (permission: ProjectPermission) => boolean;
  loading: boolean;
  switchProject: (projectId: string) => void;
  refreshProjects: () => void;
}

type ProjectPermission = "read" | "write" | "admin";

const ROLE_PERMISSIONS: Record<ProjectRole, ProjectPermission[]> = {
  owner: ["read", "write", "admin"],
  editor: ["read", "write"],
  viewer: ["read"],
};

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

const PROJECT_STORAGE_KEY = "qdash_current_project_id";

/**
 * Query parameters that name a record of one project: a chip, a cooldown, or an execution and
 * its target. An explicit project switch removes them, so the next project's pages start from
 * their own defaults instead of asking the API for the previous project's records. Filters that
 * mean the same thing in every project (dates, views, task names) are kept.
 */
const PROJECT_SCOPED_QUERY_PARAMS = [
  "chip",
  "chip_id",
  "cooldown",
  "execution",
  "executionChip",
  "executionTarget",
  "sourceTaskId",
] as const;

/** Queries whose answer does not depend on the `X-Project-Id` header. */
function isProjectIndependentQuery(query: Query): boolean {
  const head = query.queryKey[0];
  return typeof head === "string" && (head.startsWith("/projects") || head.startsWith("/auth"));
}

/**
 * Drops the cached answers of the previous project and refetches the queries on screen.
 *
 * Requests carry the project from storage, and generated query keys do not include it, so data
 * cached for one project would otherwise show under the same key in the next one (a chip ID can
 * exist in both). Resetting, unlike invalidating, also clears the data shown while the refetch
 * runs and cancels requests still in flight, so a late answer for the previous project is never
 * written to the cache.
 */
function resetProjectScopedQueries(queryClient: QueryClient) {
  void queryClient.resetQueries({
    predicate: (query) => !isProjectIndependentQuery(query),
  });
}

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { user, accessToken } = useAuth();
  const queryClient = useQueryClient();
  const pathname = usePathname();
  const [urlProjectId, setUrlProjectId] = useState<string | null>(null);
  const [urlProjectInitialized, setUrlProjectInitialized] = useState(false);
  const [currentProject, setCurrentProject] = useState<ProjectResponse | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [role, setRole] = useState<ProjectRole | null>(null);

  const {
    data: projectsData,
    isLoading,
    refetch,
  } = useListProjects({
    query: {
      enabled: !!accessToken,
      retry: false,
    },
  });

  const { data: membersData } = useListProjectMembers(projectId ?? "", {
    query: {
      enabled: !!projectId && !!accessToken,
      retry: false,
    },
  });

  // Update role when members data changes
  useEffect(() => {
    if (!membersData?.data?.members || !user?.username) {
      setRole(null);
      return;
    }
    const membership = membersData.data.members.find((m) => m.username === user.username);
    setRole((membership?.role as ProjectRole) ?? null);
  }, [membersData, user?.username]);

  const projects = useMemo(
    () => projectsData?.data?.projects ?? [],
    [projectsData?.data?.projects],
  );

  const writeProjectToUrl = useCallback(
    (
      nextProjectId: string,
      mode: "push" | "replace" = "replace",
      options: { clearProjectScopedParams?: boolean } = {},
    ) => {
      try {
        const url = new URL(window.location.href);
        url.searchParams.set("project", nextProjectId);
        if (options.clearProjectScopedParams) {
          for (const key of PROJECT_SCOPED_QUERY_PARAMS) url.searchParams.delete(key);
        }
        const nextUrl = `${url.pathname}?${url.searchParams.toString()}${url.hash}`;
        if (mode === "push") {
          window.history.pushState(null, "", nextUrl);
        } else {
          window.history.replaceState(null, "", nextUrl);
        }
        setUrlProjectId(nextProjectId);
      } catch (error) {
        console.warn("Failed to update project URL state:", error);
      }
    },
    [],
  );

  const clearProjectFromUrl = useCallback(() => {
    try {
      const url = new URL(window.location.href);
      url.searchParams.delete("project");
      const query = url.searchParams.toString();
      const nextUrl = `${url.pathname}${query ? `?${query}` : ""}${url.hash}`;
      window.history.replaceState(null, "", nextUrl);
      setUrlProjectId(null);
    } catch (error) {
      console.warn("Failed to clear project URL state:", error);
    }
  }, []);

  const readProjectFromUrl = useCallback(() => {
    const nextUrlProjectId = new URLSearchParams(window.location.search).get("project");
    setUrlProjectId(nextUrlProjectId);
    setUrlProjectInitialized(true);
    return nextUrlProjectId;
  }, []);

  useEffect(() => {
    readProjectFromUrl();
    window.addEventListener("popstate", readProjectFromUrl);
    return () => window.removeEventListener("popstate", readProjectFromUrl);
  }, [readProjectFromUrl]);

  useEffect(() => {
    const currentUrlProjectId = readProjectFromUrl();
    if (!projectId) return;
    if (currentUrlProjectId !== projectId) {
      writeProjectToUrl(projectId);
    }
  }, [pathname, projectId, readProjectFromUrl, writeProjectToUrl]);

  useEffect(() => {
    if (!urlProjectInitialized || !projects.length) return;

    const storedProjectId = localStorage.getItem(PROJECT_STORAGE_KEY);
    const urlProject = urlProjectId ? projects.find((p) => p.project_id === urlProjectId) : null;
    const storedProject = storedProjectId
      ? projects.find((p) => p.project_id === storedProjectId)
      : null;
    const defaultProject = user?.default_project_id
      ? projects.find((p) => p.project_id === user.default_project_id)
      : null;
    const nextProject = urlProject ?? storedProject ?? defaultProject ?? projects[0] ?? null;

    if (!nextProject) return;

    if (nextProject.project_id !== projectId) {
      // Requests so far carried the stored project. When the URL (a deep link, or Back to an
      // entry of another project) names a different one, their answers belong to that project.
      const requestedProjectId = localStorage.getItem(PROJECT_STORAGE_KEY);
      setCurrentProject(nextProject);
      setProjectId(nextProject.project_id);
      localStorage.setItem(PROJECT_STORAGE_KEY, nextProject.project_id);

      if (projectId !== null || requestedProjectId !== nextProject.project_id) {
        resetProjectScopedQueries(queryClient);
      }
    }

    if (urlProjectId !== nextProject.project_id) {
      writeProjectToUrl(nextProject.project_id);
    }
  }, [
    projectId,
    projects,
    queryClient,
    urlProjectId,
    urlProjectInitialized,
    user?.default_project_id,
    writeProjectToUrl,
  ]);

  useEffect(() => {
    if (!accessToken) {
      setCurrentProject(null);
      setProjectId(null);
      setRole(null);
      localStorage.removeItem(PROJECT_STORAGE_KEY);
      return;
    }

    if (!urlProjectInitialized || isLoading || projects.length > 0) return;

    setCurrentProject(null);
    setProjectId(null);
    setRole(null);
    localStorage.removeItem(PROJECT_STORAGE_KEY);
    clearProjectFromUrl();
  }, [accessToken, clearProjectFromUrl, isLoading, projects.length, urlProjectInitialized]);

  const switchProject = useCallback(
    (newProjectId: string) => {
      const project = projects.find((p) => p.project_id === newProjectId);
      if (project && project.project_id !== projectId) {
        setCurrentProject(project);
        setProjectId(project.project_id);
        localStorage.setItem(PROJECT_STORAGE_KEY, project.project_id);
        // A new history entry, so Back returns to the previous project with its chip intact.
        writeProjectToUrl(project.project_id, "push", { clearProjectScopedParams: true });
        resetProjectScopedQueries(queryClient);
      }
    },
    [projects, projectId, queryClient, writeProjectToUrl],
  );

  const refreshProjects = useCallback(() => {
    refetch();
  }, [refetch]);

  const isOwner = role === "owner";
  const isEditor = role === "editor";
  const isViewer = role === "viewer";
  const can = useCallback(
    (permission: ProjectPermission) => (role ? ROLE_PERMISSIONS[role].includes(permission) : false),
    [role],
  );
  const canEdit = can("write");

  return (
    <ProjectContext.Provider
      value={{
        currentProject,
        projects,
        projectId,
        role,
        isOwner,
        isEditor,
        isViewer,
        canEdit,
        can,
        loading: isLoading,
        switchProject,
        refreshProjects,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  const context = useContext(ProjectContext);
  if (context === undefined) {
    throw new Error("useProject must be used within a ProjectProvider");
  }
  return context;
}
