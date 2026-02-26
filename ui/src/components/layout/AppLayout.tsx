"use client";

import { usePathname } from "next/navigation";

import { Navbar } from "./Navbar";
import { Sidebar } from "./Sidebar";
import { AnalysisSidebar } from "./AnalysisSidebar";

import { SidebarProvider } from "@/contexts/SidebarContext";
import { AnalysisChatProvider } from "@/contexts/AnalysisChatContext";

interface AppLayoutProps {
  children: React.ReactNode;
}

// Pages that should not show sidebar and navbar
const PUBLIC_PATHS = ["/login"];

export function AppLayout({ children }: AppLayoutProps) {
  const pathname = usePathname();
  const isPublicPage = PUBLIC_PATHS.includes(pathname);

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
          <div className="flex-1 flex flex-col h-screen w-0">
            <Navbar />
            <main className="flex-1 overflow-y-auto bg-base-100">
              <div key={pathname} className="page-transition">
                {children}
              </div>
            </main>
          </div>
          <AnalysisSidebar />
        </div>
      </AnalysisChatProvider>
    </SidebarProvider>
  );
}
