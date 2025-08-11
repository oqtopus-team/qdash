from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.chip import ChipDocument

initialize()


chip = ChipDocument.get_current_chip(username="admin")
best_datas = {}
for qid, coupling in chip.couplings.items():
    # print(f"{qid}: {coupling.model_dump()}")
    if coupling.best_data:
        # print(f"  Best data{qid}: {coupling.best_data}")
        best_datas[qid] = coupling.best_data
        # print(f"  Best data {qid} is {coupling.best_data}")

with open("best_data.json", "w") as f:
    import json

    json.dump(best_datas, f, indent=2)

print(len(best_datas), "best datas found.")
