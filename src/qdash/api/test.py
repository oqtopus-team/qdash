from qdash.db.init.initialize import initialize
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.dbmodel.chip import ChipDocument

initialize()


def search_coupling_data_by_control_qid(cr_params, search_term):
    filtered = {}
    for key, value in cr_params.items():
        # キーが '-' を含む場合は、左側を抽出
        left_side = key.split("-")[0] if "-" in key else key
        if left_side == search_term:
            filtered[key] = value
    return filtered


if __name__ == "__main__":
    # Example usage of the CalibrationNoteDocument
    latest = (
        CalibrationNoteDocument.find({"task_id": "master"})
        .sort([("timestamp", -1)])  # 更新時刻で降順ソート
        .limit(1)
        .run()
    )[0]

    chip_docs = ChipDocument.find_one({"chip_id": "64Q", "username": latest.username}).run()
    note = latest.note

    cr_params = note["cr_params"]
    drag_hpi_params = note["drag_hpi_params"]
    drag_pi_params = note["drag_pi_params"]
    search_term = "Q31"
    print(drag_hpi_params["Q31"]["duration"])
    print(drag_pi_params["Q31"])
    print(chip_docs.qubits["31"].data["t2_echo"]["value"])
    print(chip_docs.qubits["31"].node_info.position.x)
    print(chip_docs.couplings["31-30"].data["zx90_gate_fidelity"])
    # search_result = search_coupling_data_by_control_qid(cr_params, search_term)
    # print(search_result)
    # for cr_key, cr_value in search_result.items():
    #     print(f"Key: {cr_key}, Value: {cr_value}")
    #     print(cr_value["target"])
