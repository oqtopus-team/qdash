"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { FolderLock, Settings, ShieldCheck } from "lucide-react";

import { Navbar } from "./Navbar";
import { Sidebar } from "./Sidebar";
import { AnalysisSidebar } from "./AnalysisSidebar";
import { MiniChatWindow } from "./MiniChatWindow";

import { SidebarProvider } from "@/contexts/SidebarContext";
import { AnalysisChatProvider } from "@/contexts/AnalysisChatContext";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";

interface AppLayoutProps {
  children: React.ReactNode;
}

// Pages that should not show sidebar and navbar
const PUBLIC_PATHS = ["/login"];
const PROJECT_OPTIONAL_PATH_PREFIXES = ["/admin", "/settings"];

function ProjectAccessState() {
  const { user } = useAuth();
  const isAdmin = user?.system_role === "admin";

  return (
    <div className="min-h-full flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-xl text-center">
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-base-200 text-base-content/70">
          <FolderLock size={28} aria-hidden="true" />
        </div>
        <h1 className="text-2xl font-semibold text-base-content">No project access</h1>
        <p className="mt-3 text-sm leading-6 text-base-content/70">
          You are not a member of any project yet. Ask a project owner or administrator to invite
          you before viewing measurement results, chips, workflows, or project discussions.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          {isAdmin && (
            <Link href="/admin" className="btn btn-primary gap-2">
              <ShieldCheck size={16} aria-hidden="true" />
              Open Admin
            </Link>
          )}
          <Link href="/settings" className="btn btn-outline gap-2">
            <Settings size={16} aria-hidden="true" />
            Open Settings
          </Link>
        </div>
      </div>
    </div>
  );
}

export function AppLayout({ children }: AppLayoutProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { user } = useAuth();
  const { currentProject, loading: projectLoading, projects } = useProject();
  const isPublicPage = PUBLIC_PATHS.includes(pathname);
  const isProjectOptionalPage = PROJECT_OPTIONAL_PATH_PREFIXES.some((prefix) =>
    pathname.startsWith(prefix),
  );
  const shouldRequireProject = !isPublicPage && !isProjectOptionalPage;
  const hasProjectAccess = projects.length > 0 && currentProject !== null;
  const showProjectAccessState = shouldRequireProject && !projectLoading && !hasProjectAccess;

  useEffect(() => {
    if (!isPublicPage && user?.must_change_password && pathname !== "/settings") {
      router.replace("/settings");
    }
  }, [isPublicPage, pathname, router, user?.must_change_password]);

  // Public pages (login, etc.) - render without sidebar/navbar
  if (isPublicPage) {
    return <>{children}</>;
  }

  // Authenticated pages - render with sidebar and navbar
  return (
    <SidebarProvider>
      <AnalysisChatProvider>
        <div className="flex w-full h-screen overflow-hidden">
          <Sidebar />
          <div className="flex-1 flex flex-col h-screen w-0 min-w-0 transition-[flex] duration-300 ease-in-out">
            <Navbar />
            <main className="flex-1 overflow-y-auto bg-base-100">
              <div key={pathname} className="page-transition">
                {showProjectAccessState ? <ProjectAccessState /> : children}
              </div>
            </main>
          </div>
          <AnalysisSidebar />
        </div>
        {!showProjectAccessState && <MiniChatWindow />}
      </AnalysisChatProvider>
    </SidebarProvider>
  );
}
