import json
from collections import defaultdict

# JSONファイルの読み込み
with open("best_data.json") as f:
    data = json.load(f)

# 出力用辞書の初期化
zx90_dict = defaultdict(dict)

# キー変換と値の抽出
for pair_str, values in data.items():
    ctrl, targ = map(int, pair_str.split("-"))
    qubit_key = f"Q{ctrl:02d}-Q{targ:02d}"
    base_key = f"Q{ctrl:02d}"

    # zx90_gate_fidelity の value を取得
    zx90_val = values.get("zx90_gate_fidelity", {}).get("value", None)
    zx90_dict[base_key][qubit_key] = zx90_val

# YAML構造へ整形（コメント付き）
lines = ["zx90_gate_fidelity:"]
for base_q in sorted(zx90_dict):
    lines.append(f"  # edges associated with {base_q}")
    for pair in sorted(zx90_dict[base_q]):
        val = zx90_dict[base_q][pair]
        val_str = "null" if val is None else f"{val:.15g}"
        lines.append(f"  {pair}: {val_str}")

# 保存
with open("zx90_gate_fidelity.yaml", "w") as f:
    f.write("\n".join(lines))
