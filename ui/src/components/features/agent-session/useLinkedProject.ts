"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";

/**
 * Whether the project an agent-session page belongs to is selected.
 *
 * A Slack message links to `...?project=<id>`. The browser may still carry another project in
 * storage, and requests take their project header from there, so a request sent before
 * `ProjectProvider` selects the linked project would ask the wrong project for the record. The
 * page waits until the selected project is the linked one, then pins its requests and cache
 * key to that project. A linked project the user cannot access is reported, not replaced by
 * another project. After the first selection the page follows the selected project, so an
 * explicit switch asks the new project.
 *
 * Once the signed-in user's project list has loaded and is empty, the page cannot load: a linked
 * project is reported as unavailable, and a page opened without a link reports `no_project`.
 * Neither state sends a request.
 */
export type LinkedProjectState =
  | { status: "pending" }
  | { status: "ready"; projectId: string }
  | { status: "unavailable"; projectId: string }
  | { status: "no_project" };

export function useLinkedProject(): LinkedProjectState {
  const { projectId, projects, loading } = useProject();
  const { accessToken, loading: authLoading } = useAuth();
  // undefined until the URL is read after mount, so the server and first client render match.
  const [linked, setLinked] = useState<string | null | undefined>(undefined);
  const [resolved, setResolved] = useState(false);

  useEffect(() => {
    setLinked(new URLSearchParams(window.location.search).get("project"));
  }, []);

  const matches = linked !== undefined && projectId !== null && (!linked || linked === projectId);
  useEffect(() => {
    if (matches) setResolved(true);
  }, [matches]);

  if (projectId !== null && (resolved || matches)) return { status: "ready", projectId };
  if (linked === undefined || loading) return { status: "pending" };
  // The project list is only queried with a token; before that an empty list means nothing.
  const listed = !authLoading && accessToken !== null;
  if (listed && projects.length === 0) {
    return linked ? { status: "unavailable", projectId: linked } : { status: "no_project" };
  }
  if (linked && projects.length > 0 && !projects.some((p) => p.project_id === linked)) {
    return { status: "unavailable", projectId: linked };
  }
  return { status: "pending" };
}

/** Request options that send a request to `projectId`, whatever project storage holds. */
export function projectRequest(projectId: string) {
  return { headers: { "X-Project-Id": projectId } };
}
