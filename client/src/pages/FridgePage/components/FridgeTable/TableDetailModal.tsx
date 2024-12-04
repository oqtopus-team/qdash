import "react18-json-view/src/style.css";
import JsonView from "react18-json-view";

import type { OneQubitCalibSummary } from "@/schemas";
export function TableDetailModal({
  selectedItem,
}: {
  selectedItem: OneQubitCalibSummary;
}) {
  return (
    <dialog id="tableDetail" className="modal">
      <div className="modal-box">
        <h3 className="font-bold text-lg">{selectedItem.label}</h3>
        <div style={{ textAlign: "left" }}>
          <JsonView src={selectedItem} theme="default" />
        </div>
        <div className="modal-action">
          <form method="dialog"></form>
          <form method="dialog">
            <button className="btn">Close</button>
          </form>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  );
}
