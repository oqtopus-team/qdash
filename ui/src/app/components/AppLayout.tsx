"use client";

import { usePathname } from "next/navigation";

import Navbar from "./Navbar";
import Sidebar from "./Sidebar";

import { SidebarProvider } from "@/app/contexts/SidebarContext";

interface AppLayoutProps {
  children: React.ReactNode;
}

// Pages that should not show sidebar and navbar
const PUBLIC_PATHS = ["/login"];

export default function AppLayout({ children }: AppLayoutProps) {
  const pathname = usePathname();
  const isPublicPage = PUBLIC_PATHS.includes(pathname);

  // Public pages (login, etc.) - render without sidebar/navbar
  if (isPublicPage) {
    return <>{children}</>;
  }

  // Authenticated pages - render with sidebar and navbar
  return (
    <SidebarProvider>
      <div className="flex w-full">
        <Sidebar />
        <div className="flex-1 flex flex-col min-h-screen w-0">
          <Navbar />
          <main className="flex-1 overflow-y-auto bg-base-100">{children}</main>
        </div>
      </div>
    </SidebarProvider>
  );
}
