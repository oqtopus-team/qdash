import type { DiscardPrompt } from "@/components/features/flow/useDiscardConfirmation";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

interface DiscardChangesDialogProps {
  prompt: DiscardPrompt | null;
  onConfirm: () => void;
  onDismiss: () => void;
}

/** Asks before an action drops the unsaved drafts named in `prompt`. */
export function DiscardChangesDialog({ prompt, onConfirm, onDismiss }: DiscardChangesDialogProps) {
  return (
    <ConfirmDialog
      open={prompt !== null}
      title="Discard unsaved changes?"
      description={
        <>
          Unsaved changes to{" "}
          {prompt?.names.map((draft, index) => (
            <span key={draft}>
              {index > 0 && " and "}
              <strong>{draft}.py</strong>
            </span>
          ))}{" "}
          will be lost. Save first to keep them.
        </>
      }
      confirmLabel="Discard changes"
      destructive
      onConfirm={onConfirm}
      onOpenChange={(open) => !open && onDismiss()}
    />
  );
}
