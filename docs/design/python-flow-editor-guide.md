# Python Flow Editor: ユーザーガイド

## 概要

Python Flow Editorは、UIでPythonコードを直接編集してカスタムキャリブレーションワークフローを作成できる機能です。

**作成日**: 2025-01-24
**ステータス**: 実装済み

---

## 主な機能

### 1. テンプレートベースのFlow作成

6種類のテンプレートから選択して、カスタムワークフローを作成できます：

| テンプレート            | 説明                                                              | カテゴリー |
| ----------------------- | ----------------------------------------------------------------- | ---------- |
| Simple Flow             | 基本的な単一キュービット校正                                      | basic      |
| Parallel Calibration    | タスクを複数のキュービットに並列実行（task-first）                | parallel   |
| Sequential Calibration  | 各キュービットで全タスクを順次実行（qubit-first）                 | sequential |
| Custom Parallel Flow    | グループ並列実行（例: 32→33 と 36→38 を並列）                     | parallel   |
| Adaptive Calibration    | 収束検出とイテレーション制限付き校正                              | advanced   |
| Custom Schedule Flow    | SerialNode/ParallelNode/BatchNodeによる複雑なオーケストレーション | advanced   |
| Iterative Parallel Flow | 並列グループ校正をN回繰り返し                                     | advanced   |

### 2. Monaco Editorによるコード編集

- VSCode風のシンタックスハイライト
- Python言語サポート
- 行番号とカーソル位置表示
- ミニマップ、フォールディング機能

### 3. 自動パラメータ補完

- `username`: ログインユーザーから自動取得
- `chip_id`: 最新チップから自動取得
- UIで編集可能

### 4. 実行ロック機構

- 重複実行を防止（ExecutionLock）
- 実行中は"🔒 Locked"表示
- Menu Editorと共通のロック機構

---

## テンプレート詳細

### Custom Parallel Flow

**特徴**:

- グループ内で順次実行、グループ間で並列実行
- upstream_idを正しく引き継ぎ
- エラーハンドリング付き（失敗したキュービットをスキップ）

**例**:

```python
# Group1 (33→32) と Group2 (36→38) を並列実行
group1 = ["33", "32"]
group2 = ["36", "38"]

future1 = calibrate_group.submit(qids=group1, tasks=tasks)
future2 = calibrate_group.submit(qids=group2, tasks=tasks)

results1 = future1.result()
results2 = future2.result()
```

### Iterative Parallel Flow

**特徴**:

- 並列グループ校正をN回繰り返し
- 各イテレーションで異なるパラメータを注入可能
- 安定性テストやデータ収集に最適

**例**:

```python
# 各イテレーションでCheckRabiのdetune_frequencyを変更
task_details_per_iteration = [
    None,  # Iteration 1: デフォルト (detune_frequency=0)
    {
        "CheckRabi": {
            "input_parameters": {
                "detune_frequency": {"value": 5.0}
            }
        }
    },
    {
        "CheckRabi": {
            "input_parameters": {
                "detune_frequency": {"value": 10.0}
            }
        }
    }
]
```

**動作**:

```
Iteration 1: Group1 (33→32) || Group2 (36→38) (detune=0)
Iteration 2: Group1 (33→32) || Group2 (36→38) (detune=5.0)
Iteration 3: Group1 (33→32) || Group2 (36→38) (detune=10.0)
```

---

## Python Flow Helperライブラリ

### 初期化・終了

```python
from qdash.workflow.helpers import init_calibration, finish_calibration

# 初期化（execution_id自動生成、ExecutionLock取得）
session = init_calibration(username, chip_id, qids)

# 終了（ExecutionLock解放、ChipHistory更新）
finish_calibration()
```

### タスク実行

```python
# 基本実行
result = session.execute_task("CheckRabi", "32")

# upstream_id指定
result = session.execute_task("CheckRabi", "33", upstream_id=previous_task_id)

# task_details指定（パラメータ変更）
task_details = {
    "CheckRabi": {
        "input_parameters": {
            "detune_frequency": {"value": 5.0}
        }
    }
}
result = session.execute_task("CheckRabi", "32", task_details=task_details)
```

### 並列実行パターン

```python
from prefect import task

@task
def calibrate_group(qids, tasks):
    session = get_session()
    for qid in qids:
        for task_name in tasks:
            session.execute_task(task_name, qid)

# 並列実行
future1 = calibrate_group.submit(group1, tasks)
future2 = calibrate_group.submit(group2, tasks)

results1 = future1.result()
results2 = future2.result()
```

### Adaptive実行

```python
from qdash.workflow.helpers import adaptive_calibrate

results = adaptive_calibrate(
    qids=["32"],
    tasks=["CheckRabi", "CreateHPIPulse"],
    max_iterations=5,
    convergence_threshold=0.01
)
```

---

## タスクパラメータのカスタマイズ

### CheckRabiの例

CheckRabiタスクは`preprocess`で`detune_frequency`を0に設定しますが、明示的に指定された値は保持されます。

**修正内容** (check_rabi.py):

```python
def preprocess(self, session, qid):
    super().preprocess(session, qid)

    # Only set to 0 if no value was explicitly provided via task_details
    if self.input_parameters["detune_frequency"].value is None:
        self.input_parameters["detune_frequency"].value = 0

    return PreProcessResult(input_parameters=self.input_parameters)
```

**使用例**:

```python
# デフォルト値を使用（detune_frequency=0）
result = session.execute_task("CheckRabi", "32")

# カスタム値を指定
task_details = {
    "CheckRabi": {
        "input_parameters": {
            "detune_frequency": {"value": 5.0},
            "shots": {"value": 2000}
        }
    }
}
result = session.execute_task("CheckRabi", "32", task_details=task_details)
```

---

## ファイル構造

```
/app/flows/
├── {username}/
│   └── {flow_name}.py     # ユーザーのFlowファイル

/workspace/qdash/
├── src/qdash/workflow/
│   ├── helpers/
│   │   └── flow_helpers.py           # FlowSession, helper関数
│   └── examples/
│       └── templates/
│           ├── simple_flow.py
│           ├── parallel_flow.py
│           ├── sequential_flow.py
│           ├── custom_parallel_flow.py   # ← NEW
│           ├── adaptive_flow.py
│           ├── schedule_flow.py
│           ├── iterative_flow.py         # ← NEW
│           └── templates.json
```

---

## UI操作フロー

### 新しいFlowを作成

1. `/flow/new` ページにアクセス
2. テンプレートを選択（デフォルト: Simple Flow）
3. Flow名、説明、パラメータを編集
4. コードを編集（Monaco Editor）
5. "Save Flow"ボタンをクリック

### 既存のFlowを編集・実行

1. `/flow` ページでFlowリストを表示
2. Flowをクリックして編集ページへ
3. コードやパラメータを編集
4. "Save Changes"で保存
5. "▶ Execute"で実行（ロック確認）
6. 実行中は"🔒 Locked"表示

---

## トラブルシューティング

### Q: パラメータが変更されない

A: `task_details`のフォーマットを確認してください：

```python
# ✅ 正しい
task_details = {
    "CheckRabi": {
        "input_parameters": {
            "detune_frequency": {"value": 5.0}
        }
    }
}

# ❌ 間違い
task_details = {"CheckRabi": {"detune_frequency": 5.0}}
```

### Q: 並列実行されない

A: `execute_schedule()`は`ParallelNode`でも順次実行します。真の並列実行には`.submit()`を使用してください：

```python
# ❌ 順次実行
schedule = ParallelNode(parallel=["0", "1"])
execute_schedule(tasks, schedule)

# ✅ 並列実行
future1 = calibrate_group.submit(group1, tasks)
future2 = calibrate_group.submit(group2, tasks)
```

### Q: upstream_idが他のグループのタスクを参照してしまう

A: `FlowSession`は各qidごとにupstream_idを記録します。グループ内で順次実行する場合、`upstream_id`を明示的に渡してください。

---

## まとめ

Python Flow Editorを使用することで：

- ✅ クローズドループ校正
- ✅ 条件分岐
- ✅ 動的な並列・直列実行
- ✅ 柔軟なパラメータ管理
- ✅ イテレーション実行とパラメータスイープ

が可能になります。テンプレートから始めて、ニーズに応じてカスタマイズしてください。
