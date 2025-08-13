"use client";

import { useRouter } from "next/navigation";

import type { Menu } from "../../model";

interface EditConfirmModalProps {
  selectedItem: Menu;
  onCancel: () => void;
}

export function EditConfirmModal({
  selectedItem,
  onCancel,
}: EditConfirmModalProps) {
  const router = useRouter();

  const handleConfirm = () => {
    router.push(`/menu/editor?name=${selectedItem.name}`);
  };

  return (
    <dialog id="editConfirm" className="modal modal-bottom sm:modal-middle">
      <div className="modal-box">
        <h3 className="font-bold text-lg">Edit Menu</h3>
        <p className="py-4">
          メニュー「{selectedItem.name}
          」を編集します。エディタページに移動しますか？
        </p>
        <div className="modal-action">
          <form method="dialog">
            <button className="btn btn-ghost mr-2" onClick={onCancel}>
              Cancel
            </button>
            <button className="btn btn-primary" onClick={handleConfirm}>
              Edit
            </button>
          </form>
        </div>
      </div>
    </dialog>
  );
}
