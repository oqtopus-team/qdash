"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Navbar } from "./Navbar";
import { Sidebar } from "./Sidebar";
import { AnalysisSidebar } from "./AnalysisSidebar";
import { MiniChatWindow } from "./MiniChatWindow";

import { SidebarProvider } from "@/contexts/SidebarContext";
import { AnalysisChatProvider } from "@/contexts/AnalysisChatContext";
import { useAuth } from "@/contexts/AuthContext";

interface AppLayoutProps {
  children: React.ReactNode;
}

// Pages that should not show sidebar and navbar
const PUBLIC_PATHS = ["/login"];

export function AppLayout({ children }: AppLayoutProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { user } = useAuth();
  const isPublicPage = PUBLIC_PATHS.includes(pathname);

  useEffect(() => {
    if (
      !isPublicPage &&
      user?.must_change_password &&
      pathname !== "/settings"
    ) {
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
                {children}
              </div>
            </main>
          </div>
          <AnalysisSidebar />
        </div>
        <MiniChatWindow />
      </AnalysisChatProvider>
    </SidebarProvider>
  );
}
