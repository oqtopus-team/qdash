# Python Flow Implementation Plan for QDash

## 概要

QDashにPython Flow Editorを導入し、クローズドループキャリブレーションや複雑な条件分岐を可能にする実装計画。

**作成日**: 2025-01-22
**ステータス**: 設計フェーズ

---

## 背景と課題

### 現状のMenu Editorの制約

現在のMenu Editorは以下の制約があり、クローズドループキャリブレーションには不向き:

1. **静的なタスクリスト**: 実行前に決定された線形タスクリストのみ対応
2. **限定的なフィードバック**: タスク間のパラメータ引き継ぎが手動
3. **収束条件の欠如**: 「収束するまで繰り返す」などのロジックを表現できない
4. **条件分岐の不在**: 測定結果に応じたワークフロー変更ができない

### 求められる機能

- ✅ クローズドループ（収束まで繰り返し）
- ✅ 条件分岐（測定結果に応じた処理変更）
- ✅ 動的な並列・シリアル実行
- ✅ 柔軟なパラメータ管理

---

## 採用する方針

### **Python Flow Editor: Prefectを直接記述**

独自DSLを作るのではなく、**Pythonコードを直接編集できるUI**を提供する。

#### 理由

1. **Prefectは既に完璧なDSL**: デコレータベースで十分な表現力
2. **学習曲線の問題**: 独自DSLよりPython/Prefect学習の方が汎用的
3. **柔軟性**: 複雑なロジックもストレートに記述可能
4. **メンテナンス**: 独自DSLのメンテナンスコスト不要

#### 2つのモード提供

```
┌─────────────────────────────────────┐
│  Menu Editor (Simple Mode)          │  ← 既存、シンプルなケース向け
│  - ノーコード                        │
│  - 定型的なキャリブレーション          │
│  - 初心者向け                        │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Python Editor (Advanced Mode)      │  ← 新規、複雑なケース向け
│  - フルコード                        │
│  - クローズドループ、条件分岐         │
│  - パワーユーザー向け                 │
└─────────────────────────────────────┘
```

---

## アーキテクチャ設計

### データベース分離

```python
# 既存: MenuDocument (変更なし)
class MenuDocument(Document):
    name: str
    username: str
    tasks: list[str]
    schedule: dict
    task_details: dict
    # ...

# 新規: FlowDocument (追加)
class FlowDocument(Document):
    name: str
    username: str
    code: str  # Pythonコード
    description: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    class Settings:
        name = "flows"  # 別コレクション
```

### APIルート分離

```python
# src/qdash/api/main.py
app.include_router(menu_router, prefix="/api", tags=["menu"])  # 既存
app.include_router(flow_router, prefix="/api", tags=["flow"])  # 新規
```

### UIルート分離

```
ui/src/app/
├── menu/editor/           # 既存Menu Editor (変更なし)
├── flow/editor/           # 新規Python Flow Editor
└── calibration/           # 実行画面（両方から起動可能）
```

---

## シンプルな実装設計

### 基本方針

**複雑な実行グラフは作らない。Prefectに任せる。**

QDashが提供すべきもの:
1. タスク結果の保存（パラメータ、測定データ）
2. 実行メタデータ（誰が、いつ、何を）
3. Prefect Flow Run IDとの紐付け

### データモデル（最小限）

```python
# src/qdash/dbmodel/calibration_result.py
class CalibrationResultDocument(Document):
    """キャリブレーション結果（Menu/Flow共通）"""

    # 基本情報
    execution_id: str
    username: str
    chip_id: str
    workflow_name: str
    workflow_type: str  # "menu" or "flow"

    # Prefect連携
    flow_run_id: str  # Prefect Flow Run ID

    # 結果データ
    results: dict  # {"q0": {"frequency": 5.0, "t1": 20.0}, ...}

    # メタデータ
    started_at: datetime
    finished_at: datetime | None
    status: str

    class Settings:
        name = "calibration_results"

# src/qdash/dbmodel/task_result_history.py
class TaskResultHistoryDocument(Document):
    """個別タスクの履歴"""

    execution_id: str
    task_name: str
    qid: str | None
    output_parameters: dict
    raw_data: dict | None
    timestamp: datetime
    status: str
    iteration: int | None = None  # ループの場合

    class Settings:
        name = "task_result_history"
```

---

## QDashヘルパー関数

### 設計思想

ユーザーに書いてもらいたいこと:
- ✅ キャリブレーションの戦略
- ✅ 収束条件
- ✅ 条件分岐

QDashが提供すること:
- ✅ 並列・シリアル実行の簡単なAPI
- ✅ クローズドループの定型パターン
- ✅ DB保存の自動化
- ✅ セッション管理

### 提供するヘルパー関数

```python
# src/qdash/workflow/helpers.py

# === 基本 ===
init_calibration(username, execution_id, chip_id, backend="qubex")
get_session(qids=None)
finish_calibration(results)

# === 並列実行 ===
calibrate_qubits_parallel(qids, tasks, backend="qubex")
calibrate_qubits_serial(qids, tasks, backend="qubex")
calibrate_qubits_batch(qids, tasks, backend="qubex")

# === クローズドループ ===
adaptive_calibrate(qid, measure_func, update_func, converge_func, max_iterations=10)
adaptive_calibrate_parallel(qids, measure_func, update_func, converge_func, max_iterations=10)

# === 結果保存 ===
save_task_result(task_name, qid, result, iteration=None)
get_parameter(qid, param_name)
set_parameter(qid, param_name, value)
```

### 使用例

#### 例1: シンプルな並列キャリブレーション

```python
from prefect import flow
from qdash.workflow.helpers import (
    init_calibration,
    calibrate_qubits_parallel,
    finish_calibration
)

@flow
def simple_calibration(username, execution_id, chip_id, qids):
    init_calibration(username, execution_id, chip_id)

    results = calibrate_qubits_parallel(
        qids=qids,
        tasks=["CheckFreq", "CheckRabi", "CheckT1", "CheckT2Echo"]
    )

    finish_calibration(results)
    return results
```

#### 例2: 適応的周波数キャリブレーション

```python
from prefect import flow
from qdash.workflow.helpers import (
    init_calibration,
    adaptive_calibrate_parallel,
    get_session,
    finish_calibration
)

@flow
def adaptive_frequency_calibration(
    username, execution_id, chip_id, qids, threshold=0.01
):
    init_calibration(username, execution_id, chip_id)
    session = get_session(qids)

    # 測定関数
    def measure(qid, iteration):
        current_freq = get_parameter(qid, "qubit_frequency") or 5.0
        result = session.measure_spectroscopy(qid, current_freq, span=0.1)
        fitted_freq = analyze_spectroscopy(result)
        return {"fitted_frequency": fitted_freq}

    # 更新関数
    def update(qid, result):
        session.update_parameter(
            qid, "qubit_frequency", result["fitted_frequency"]
        )

    # 収束判定
    def converged(history):
        if len(history) < 2:
            return False
        diff = abs(history[-1]["fitted_frequency"] - history[-2]["fitted_frequency"])
        return diff < threshold

    # 実行
    results = adaptive_calibrate_parallel(
        qids=qids,
        measure_func=measure,
        update_func=update,
        converge_func=converged,
        max_iterations=10
    )

    finish_calibration(results)
    return results
```

#### 例3: 条件分岐を含むキャリブレーション

```python
from prefect import flow
from qdash.workflow.helpers import (
    init_calibration,
    get_session,
    calibrate_qubits_parallel
)

@flow
def smart_calibration(username, execution_id, chip_id, qids):
    init_calibration(username, execution_id, chip_id)
    session = get_session(qids)

    results = {}

    for qid in qids:
        # 初期チェック
        status = check_qubit_status(session, qid)

        if status["noise_level"] > 0.5:
            # ノイズが高い → 特別なプロトコル
            results[qid] = calibrate_qubits_parallel(
                qids=[qid],
                tasks=["NoiseReduction", "CheckFreq", "CheckRabi"]
            )
        elif status["t1"] < 10:
            # T1が短い → relaxation重視
            results[qid] = calibrate_qubits_parallel(
                qids=[qid],
                tasks=["OptimizeT1", "CheckFreq"]
            )
        else:
            # 通常のキャリブレーション
            results[qid] = calibrate_qubits_parallel(
                qids=[qid],
                tasks=["CheckFreq", "CheckRabi", "CheckT1", "CheckT2"]
            )

    finish_calibration(results)
    return results
```

---

## UI実装

### Python Flow Editor

```typescript
// ui/src/app/flow-editor/page.tsx
"use client";

import Editor from "@monaco-editor/react";
import { useState } from "react";

export default function FlowEditor() {
  const [code, setCode] = useState(defaultFlowTemplate);
  const [executing, setExecuting] = useState(false);

  const handleExecute = async () => {
    setExecuting(true);
    try {
      const response = await executeFlow({ code, chip_id });
      // 実行結果を表示
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div className="grid grid-cols-2 gap-4 h-screen">
      {/* Left: Code Editor */}
      <div className="flex flex-col">
        <div className="toolbar">
          <button onClick={handleExecute} disabled={executing}>
            {executing ? "Running..." : "▶ Execute"}
          </button>
          <button onClick={handleSave}>💾 Save</button>
        </div>

        <Editor
          language="python"
          value={code}
          onChange={setCode}
          options={{
            minimap: { enabled: true },
            fontSize: 14,
            theme: "vs-dark",
          }}
        />
      </div>

      {/* Right: Execution Monitor */}
      <div className="flex flex-col">
        <ExecutionDAG flowRunId={currentFlowRunId} />
        <LogViewer logs={logs} />
        <ResultsPanel results={results} />
      </div>
    </div>
  );
}
```

### セキュリティ対策

```python
# src/qdash/api/lib/code_security.py
import ast

ALLOWED_IMPORTS = {
    "prefect", "prefect.task", "prefect.flow",
    "qdash.workflow", "qdash.workflow.tasks",
    "numpy", "matplotlib", "plotly",
}

FORBIDDEN_MODULES = {
    "os", "sys", "subprocess", "eval", "exec",
    "__import__", "open", "file",
}

class SecurityVisitor(ast.NodeVisitor):
    """ASTを走査して危険なコードを検出"""

    def __init__(self):
        self.violations = []

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name not in ALLOWED_IMPORTS:
                self.violations.append(f"Forbidden import: {alias.name}")

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_MODULES:
                self.violations.append(f"Forbidden function: {node.func.id}")
        self.generic_visit(node)

def is_safe_code(code: str) -> bool:
    """コードの安全性を検証"""
    try:
        tree = ast.parse(code)
        visitor = SecurityVisitor()
        visitor.visit(tree)
        return len(visitor.violations) == 0
    except:
        return False
```

---

## 実装ロードマップ

### Week 1: 基本ヘルパー実装

**新規ファイル**:
```bash
src/qdash/workflow/helpers.py
src/qdash/dbmodel/flow.py
src/qdash/api/routers/flow.py
```

**実装内容**:
- `init_calibration()`
- `get_session()`
- `calibrate_qubits_parallel()`
- `finish_calibration()`
- `save_task_result()`

**目標**: 80%のユースケースをカバー

### Week 2: Python Flow Editor UI

**新規ファイル**:
```bash
ui/src/app/flow/editor/page.tsx
ui/src/app/flow/list/page.tsx
```

**実装内容**:
- Monaco Editorの統合
- 実行APIエンドポイント
- 基本的なセキュリティチェック
- テンプレート機能

### Week 3: クローズドループヘルパー

**実装内容**:
- `adaptive_calibrate()`
- `adaptive_calibrate_parallel()`
- `calibrate_qubits_serial()`
- `calibrate_qubits_batch()`

### Week 4: 統合・テスト

**実装内容**:
- Calibrationページに統合
- Menu/Flow両方の実行対応
- リアルタイムログ表示
- 結果可視化の拡張
- E2Eテスト

### Week 5以降: 高度な機能

- インテリセンス・補完
- Git連携
- フローテンプレートライブラリ
- コードレビュー機能

---

## 既存Menuとの共存

### 移行戦略

**Phase 1: 並行運用**
- 既存Menu → 現状維持
- 新規Flow → 新機能として追加
- どちらも選択可能

**Phase 2: 相互変換**
- Menu → Python変換ツール提供
- ユーザーは好きなタイミングで移行

**Phase 3: 長期的**
- Menuはシンプルケース向けに維持
- Flowは複雑ケース向けに発展

### 後方互換性

```python
# src/qdash/api/routers/calibration.py
@router.post("/calibration/execute")
async def execute_calibration(request: ExecuteRequest):
    """MenuまたはFlowを実行"""

    menu_doc = MenuDocument.find_one({"name": request.name}).run()
    flow_doc = FlowDocument.find_one({"name": request.name}).run()

    if menu_doc:
        # 既存のMenu実行（変更なし）
        return await execute_menu_workflow(menu_doc)

    elif flow_doc:
        # Python Flow実行
        return await execute_python_flow(flow_doc)

    else:
        raise HTTPException(404, "Workflow not found")
```

---

## 実行履歴の管理

### Prefect UIとの連携

**QDash UI**: 結果データの確認
- キャリブレーション結果（パラメータ値）
- 測定データ
- サマリー統計

**Prefect UI**: 実行詳細の確認
- タスクの実行順序
- ログ
- エラー詳細
- 実行時間

### UI統合

```typescript
// 実行詳細ページにPrefect UIへのリンクを追加
<a href={`http://prefect-server:4200/flow-runs/${flow_run_id}`}>
  View detailed execution in Prefect UI →
</a>
```

---

## セキュリティ考慮事項

### コード実行の制限

1. **静的解析**: AST解析で危険なコード検出
2. **インポート制限**: ホワイトリスト方式
3. **実行環境分離**: コンテナベースの実行
4. **ユーザー権限**: 実行可能ユーザーの制限

### 将来的な拡張

- サンドボックス実行環境
- リソース制限（CPU、メモリ、時間）
- コードレビュープロセス
- 承認フロー

---

## メリット・デメリット

### メリット

✅ **柔軟性**: クローズドループ、条件分岐、複雑なロジックすべて可能
✅ **学習曲線**: Python/Prefectは汎用的なスキル
✅ **メンテナンス**: 独自DSL不要
✅ **エコシステム**: Prefectの機能をフル活用
✅ **後方互換性**: 既存Menuは変更なし
✅ **段階的移行**: ユーザーは好きなタイミングで移行可能

### デメリット（と対策）

❌ **Pythonの知識が必要**
→ 対策: テンプレート提供、ドキュメント充実

❌ **セキュリティリスク**
→ 対策: 静的解析、サンドボックス実行

❌ **初心者には難しい**
→ 対策: Simple Mode (Menu Editor) を維持

---

## 次のアクション

### 即座に開始可能

1. **ヘルパー関数のプロトタイプ実装**
   - `calibrate_qubits_parallel()` の実装
   - テスト用Flowの作成

2. **基本的なAPI実装**
   - `/api/flow` エンドポイント
   - FlowDocumentスキーマ

3. **最小限のUI実装**
   - Monaco Editorの統合
   - 実行ボタン

### 質問・確認事項

- [ ] セキュリティ要件の詳細確認
- [ ] 実行環境（コンテナ）の設計
- [ ] ユーザー権限管理の方針
- [ ] テンプレートの内容

---

## 参考資料

- [Prefect Documentation](https://docs.prefect.io/)
- [Monaco Editor](https://microsoft.github.io/monaco-editor/)
- [Python AST Module](https://docs.python.org/3/library/ast.html)
- QDash既存実装: `src/qdash/workflow/core/calibration/flow.py`

---

## 変更履歴

| 日付 | 変更内容 | 著者 |
|------|---------|------|
| 2025-01-22 | 初版作成 | - |
