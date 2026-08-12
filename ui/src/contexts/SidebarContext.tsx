"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";

interface SidebarContextType {
  isOpen: boolean;
  isMobileOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleMobileSidebar: () => void;
  setMobileSidebarOpen: (open: boolean) => void;
}

const SidebarContext = createContext<SidebarContextType | undefined>(undefined);

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(true);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);

  // Load sidebar state from localStorage on mount
  useEffect(() => {
    const savedState = localStorage.getItem("sidebar-open");
    if (savedState !== null) {
      setIsOpen(savedState === "true");
    }
    setIsInitialized(true);
  }, []);

  useEffect(() => {
    if (!isMobileOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsMobileOpen(false);
      }
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMobileOpen]);

  // Save sidebar state to localStorage when it changes
  useEffect(() => {
    if (isInitialized) {
      localStorage.setItem("sidebar-open", String(isOpen));
    }
  }, [isOpen, isInitialized]);

  // Close mobile sidebar when route changes or on resize
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 1024) {
        setIsMobileOpen(false);
      }
    };

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const toggleSidebar = useCallback(() => {
    setIsOpen((prev) => !prev);
  }, []);

  const setSidebarOpen = useCallback((open: boolean) => {
    setIsOpen(open);
  }, []);

  const toggleMobileSidebar = useCallback(() => {
    setIsMobileOpen((prev) => !prev);
  }, []);

  const setMobileSidebarOpen = useCallback((open: boolean) => {
    setIsMobileOpen(open);
  }, []);

  return (
    <SidebarContext.Provider
      value={{
        isOpen,
        isMobileOpen,
        toggleSidebar,
        setSidebarOpen,
        toggleMobileSidebar,
        setMobileSidebarOpen,
      }}
    >
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar() {
  const context = useContext(SidebarContext);
  if (context === undefined) {
    throw new Error("useSidebar must be used within a SidebarProvider");
  }
  return context;
}
