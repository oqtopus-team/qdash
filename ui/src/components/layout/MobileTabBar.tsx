"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Ellipsis } from "lucide-react";

import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useSidebar } from "@/contexts/SidebarContext";
import {
  getMobileTabs,
  getNavigationSections,
  isMobileOverflowActive,
  isMobileTabActive,
} from "@/components/layout/navigation";

// The circular icon background marks the current tab, so DaisyUI's dock underline
// (`::after`) is hidden and its item bottom margin is removed.
const TAB_CLASS =
  "mb-0 min-w-11 gap-0.5 after:hidden focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";
const ACTIVE_ICON_CLASS = "bg-primary/15 text-primary";
const ACTIVE_LABEL_CLASS = "font-medium text-primary";
const INACTIVE_CLASS = "text-base-content/70";

/** Icon circle and label shared by the route tabs and the More button. */
function TabFace({ icon, label, active }: { icon: ReactNode; label: string; active: boolean }) {
  return (
    <>
      <span
        data-testid="mobile-tab-icon"
        className={`flex size-8 items-center justify-center rounded-full transition-colors ${
          active ? ACTIVE_ICON_CLASS : ""
        }`}
      >
        {icon}
      </span>
      <span className={`dock-label text-xs ${active ? ACTIVE_LABEL_CLASS : ""}`}>{label}</span>
    </>
  );
}

/**
 * Bottom tab bar for viewports below `lg`, where the desktop rail is hidden. It
 * sits in the layout flow under `main`, so page content, editors, and floating
 * controls end above it instead of under it. The `nav` reserves the inset gap
 * around a rounded DaisyUI dock surface plus the bottom safe-area inset, and
 * its top edge is what `MiniChatWindow` measures. The last item, More, opens
 * the bottom sheet that `Sidebar` renders with every destination the tabs omit;
 * it reads as current while that sheet is open or one of its routes is showing.
 */
export function MobileTabBar() {
  const pathname = usePathname();
  const { canEdit } = useProject();
  const { user } = useAuth();
  const { isMobileOpen, toggleMobileSidebar } = useSidebar();
  const sections = getNavigationSections({ canEdit, isAdmin: user?.system_role === "admin" });
  const tabs = getMobileTabs(sections);
  // While the sheet is open, More is the only highlighted item.
  const moreActive = isMobileOpen || isMobileOverflowActive(sections, pathname);

  return (
    <nav
      id="mobile-tab-bar"
      aria-label="Primary navigation"
      className="relative z-20 shrink-0 bg-base-100 px-3 pt-1 pb-[calc(0.75rem+env(safe-area-inset-bottom))] lg:hidden"
    >
      <div className="dock relative h-16 rounded-2xl border border-base-content/10 p-1 shadow-xs">
        {tabs.map((tab) => {
          const Icon = tab.item.icon;
          const current = isMobileTabActive(tab, pathname);
          // The route keeps `aria-current`; only the highlight moves to an open More.
          const active = current && !isMobileOpen;
          return (
            <Link
              key={tab.item.href}
              href={tab.item.href}
              aria-current={current ? "page" : undefined}
              className={`${TAB_CLASS} ${active ? "" : INACTIVE_CLASS}`}
            >
              <TabFace
                icon={<Icon size={18} aria-hidden="true" />}
                label={tab.item.label}
                active={active}
              />
            </Link>
          );
        })}
        <button
          type="button"
          onClick={toggleMobileSidebar}
          aria-haspopup="dialog"
          aria-expanded={isMobileOpen}
          data-active={moreActive ? "true" : undefined}
          className={`${TAB_CLASS} ${moreActive ? "" : INACTIVE_CLASS}`}
        >
          <TabFace
            icon={<Ellipsis size={18} aria-hidden="true" />}
            label="More"
            active={moreActive}
          />
        </button>
      </div>
    </nav>
  );
}
