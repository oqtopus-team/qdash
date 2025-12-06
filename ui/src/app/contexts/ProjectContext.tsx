"use client";

import type { ReactNode } from "react";
import {
  createContext,
  useCallback,
  useContext,
  useState,
  useEffect,
} from "react";

import type { ProjectResponse, ProjectRole } from "@/schemas";
import {
  useListProjects,
  useListProjectMembers,
} from "@/client/projects/projects";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "./AuthContext";

interface ProjectContextType {
  currentProject: ProjectResponse | null;
  projects: ProjectResponse[];
  projectId: string | null;
  role: ProjectRole | null;
  isOwner: boolean;
  isEditor: boolean;
  isViewer: boolean;
  canEdit: boolean;
  loading: boolean;
  switchProject: (projectId: string) => void;
  refreshProjects: () => void;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

const PROJECT_STORAGE_KEY = "qdash_current_project_id";

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { user, accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [currentProject, setCurrentProject] = useState<ProjectResponse | null>(
    null
  );
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
    const membership = membersData.data.members.find(
      (m) => m.username === user.username
    );
    setRole((membership?.role as ProjectRole) ?? null);
  }, [membersData, user?.username]);

  const projects = projectsData?.data?.projects ?? [];

  useEffect(() => {
    if (!projects.length) return;

    const storedProjectId = localStorage.getItem(PROJECT_STORAGE_KEY);
    if (storedProjectId) {
      const storedProject = projects.find(
        (p) => p.project_id === storedProjectId
      );
      if (storedProject) {
        setCurrentProject(storedProject);
        setProjectId(storedProject.project_id);
        return;
      }
    }

    if (user?.default_project_id) {
      const defaultProject = projects.find(
        (p) => p.project_id === user.default_project_id
      );
      if (defaultProject) {
        setCurrentProject(defaultProject);
        setProjectId(defaultProject.project_id);
        localStorage.setItem(PROJECT_STORAGE_KEY, defaultProject.project_id);
        return;
      }
    }

    if (projects.length > 0) {
      const firstProject = projects[0];
      setCurrentProject(firstProject);
      setProjectId(firstProject.project_id);
      localStorage.setItem(PROJECT_STORAGE_KEY, firstProject.project_id);
    }
  }, [projects, user?.default_project_id]);

  const switchProject = useCallback(
    (newProjectId: string) => {
      const project = projects.find((p) => p.project_id === newProjectId);
      if (project && project.project_id !== projectId) {
        setCurrentProject(project);
        setProjectId(project.project_id);
        localStorage.setItem(PROJECT_STORAGE_KEY, project.project_id);
        // Invalidate all queries to refresh data for new project
        queryClient.invalidateQueries();
      }
    },
    [projects, projectId, queryClient]
  );

  const refreshProjects = useCallback(() => {
    refetch();
  }, [refetch]);

  const isOwner = role === "owner";
  const isEditor = role === "editor";
  const isViewer = role === "viewer";
  const canEdit = isOwner || isEditor;

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
