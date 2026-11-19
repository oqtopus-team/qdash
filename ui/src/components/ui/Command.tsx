"use client";

import { Command as CommandPrimitive } from "cmdk";
import { Search } from "lucide-react";
import type { ComponentPropsWithoutRef, ElementRef } from "react";
import { forwardRef, useRef } from "react";
import { twMerge } from "tailwind-merge";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";

export const Command = forwardRef<
  ElementRef<typeof CommandPrimitive>,
  ComponentPropsWithoutRef<typeof CommandPrimitive>
>(({ className, ...props }, ref) => (
  <CommandPrimitive ref={ref} className={twMerge("text-base-content", className)} {...props} />
));
Command.displayName = CommandPrimitive.displayName;

export const CommandInput = forwardRef<
  ElementRef<typeof CommandPrimitive.Input>,
  ComponentPropsWithoutRef<typeof CommandPrimitive.Input>
>(({ className, ...props }, ref) => (
  <div className="flex items-center gap-2.5 border-b border-base-content/10 px-4">
    <Search size={16} className="shrink-0 text-base-content/40" aria-hidden="true" />
    <CommandPrimitive.Input
      ref={ref}
      className={twMerge(
        "h-12 min-w-0 flex-1 bg-transparent text-sm text-base-content outline-none placeholder:text-base-content/40",
        className,
      )}
      {...props}
    />
  </div>
));
CommandInput.displayName = CommandPrimitive.Input.displayName;

export const CommandList = forwardRef<
  ElementRef<typeof CommandPrimitive.List>,
  ComponentPropsWithoutRef<typeof CommandPrimitive.List>
>(({ className, ...props }, ref) => (
  <CommandPrimitive.List
    ref={ref}
    className={twMerge(
      "max-h-[min(24rem,calc(100dvh-9rem))] scroll-py-1.5 overflow-y-auto overscroll-contain p-1.5",
      className,
    )}
    {...props}
  />
));
CommandList.displayName = CommandPrimitive.List.displayName;

export const CommandEmpty = forwardRef<
  ElementRef<typeof CommandPrimitive.Empty>,
  ComponentPropsWithoutRef<typeof CommandPrimitive.Empty>
>(({ className, ...props }, ref) => (
  <CommandPrimitive.Empty
    ref={ref}
    className={twMerge("px-3 py-8 text-center text-sm text-base-content/50", className)}
    {...props}
  />
));
CommandEmpty.displayName = CommandPrimitive.Empty.displayName;

export const CommandItem = forwardRef<
  ElementRef<typeof CommandPrimitive.Item>,
  ComponentPropsWithoutRef<typeof CommandPrimitive.Item>
>(({ className, ...props }, ref) => (
  <CommandPrimitive.Item
    ref={ref}
    className={twMerge(
      "flex min-h-9 cursor-pointer select-none items-center gap-3 rounded-field px-2.5 py-2 text-sm text-base-content outline-none data-[selected=true]:bg-base-200 data-[disabled=true]:cursor-not-allowed data-[disabled=true]:text-base-content/30",
      className,
    )}
    {...props}
  />
));
CommandItem.displayName = CommandPrimitive.Item.displayName;

export const CommandGroup = forwardRef<
  ElementRef<typeof CommandPrimitive.Group>,
  ComponentPropsWithoutRef<typeof CommandPrimitive.Group>
>(({ className, ...props }, ref) => (
  <CommandPrimitive.Group
    ref={ref}
    className={twMerge(
      "[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-base-content/50",
      className,
    )}
    {...props}
  />
));
CommandGroup.displayName = CommandPrimitive.Group.displayName;

interface CommandDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  children: React.ReactNode;
}

export function CommandDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
}: CommandDialogProps) {
  // The palette opens from shortcuts as well as buttons, so there is no Radix trigger to return
  // to; it remembers what had focus when it opened and gives focus back there when it closes.
  const returnFocusRef = useRef<HTMLElement | null>(null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Floats near the top like a launcher; `command-palette*` own the entrance and exit motion. */}
      <DialogContent
        className="command-palette top-3 w-[calc(100%-1.5rem)] max-w-[40rem] translate-y-0 overflow-hidden border-base-content/10 bg-base-100 p-0 sm:top-[12vh]"
        overlayClassName="command-palette-overlay bg-black/25"
        onOpenAutoFocus={() => {
          returnFocusRef.current =
            document.activeElement instanceof HTMLElement ? document.activeElement : null;
        }}
        onCloseAutoFocus={(event) => {
          const returnFocus = returnFocusRef.current;
          returnFocusRef.current = null;
          if (!returnFocus?.isConnected) return;
          event.preventDefault();
          returnFocus.focus({ preventScroll: true });
        }}
      >
        <DialogTitle className="sr-only">{title}</DialogTitle>
        <DialogDescription className="sr-only">{description}</DialogDescription>
        {children}
      </DialogContent>
    </Dialog>
  );
}
