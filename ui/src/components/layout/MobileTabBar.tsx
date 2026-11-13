"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import {
  getMobileTabs,
  getNavigationSections,
  isMobileTabActive,
} from "@/components/layout/navigation";

const ACTIVE_TAB_CLASS = "dock-active bg-primary/12 text-primary";
const INACTIVE_TAB_CLASS = "text-base-content/70";

/**
 * Bottom tab bar for viewports below `lg`, where the desktop rail is hidden. It
 * sits in the layout flow under `main`, so page content, editors, and floating
 * controls end above it instead of under it. DaisyUI's dock pads the bar by the
 * bottom safe-area inset. Every destination the tabs omit stays in the header
 * menu.
 */
export function MobileTabBar() {
  const pathname = usePathname();
  const { canEdit } = useProject();
  const { user } = useAuth();
  const tabs = getMobileTabs(
    getNavigationSections({ canEdit, isAdmin: user?.system_role === "admin" }),
  );

  return (
    <nav
      id="mobile-tab-bar"
      aria-label="Primary navigation"
      className="dock relative z-20 shrink-0 border-base-300 lg:hidden"
    >
      {tabs.map((tab) => {
        const Icon = tab.item.icon;
        const active = isMobileTabActive(tab, pathname);
        return (
          <Link
            key={tab.item.href}
            href={tab.item.href}
            aria-current={active ? "page" : undefined}
            className={`transition-colors ${active ? ACTIVE_TAB_CLASS : INACTIVE_TAB_CLASS}`}
          >
            <Icon size={18} aria-hidden="true" />
            <span className="dock-label text-xs">{tab.item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
