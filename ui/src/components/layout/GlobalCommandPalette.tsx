"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getNavigationSections } from "@/components/layout/navigation";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/Command";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";

export function GlobalCommandPalette() {
  const router = useRouter();
  const { user } = useAuth();
  const { canEdit } = useProject();
  const [open, setOpen] = useState(false);
  const sections = getNavigationSections({
    canEdit,
    isAdmin: user?.system_role === "admin",
  });

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((current) => !current);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const navigate = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="btn btn-ghost btn-sm gap-2 text-base-content/60"
        aria-label="Open navigation search"
      >
        <Search size={15} aria-hidden="true" />
        <span className="hidden sm:inline">Navigate</span>
        <kbd className="hidden rounded border border-base-300 bg-base-200 px-1.5 py-0.5 text-xs font-normal md:inline">
          ⌘K
        </kbd>
      </button>

      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Navigate"
        description="Search for a page to open."
      >
        <Command loop label="QDash navigation">
          <CommandInput placeholder="Search pages..." />
          <CommandList>
            <CommandEmpty>No matching pages</CommandEmpty>
            {sections.map((section) => {
              const items = section.items.filter((item) => item.visible !== false);
              if (items.length === 0) return null;

              return (
                <CommandGroup key={section.label} heading={section.label}>
                  {items.map((item) => (
                    <CommandItem
                      key={item.href}
                      value={item.label}
                      keywords={[item.href, section.label]}
                      onSelect={() => navigate(item.href)}
                    >
                      <item.icon size={15} className="shrink-0 opacity-60" aria-hidden="true" />
                      <span>{item.label}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              );
            })}
          </CommandList>
        </Command>
      </CommandDialog>
    </>
  );
}
