# QDash Python Flow Editor: 実装サマリー

## 概要

**実装期間**: 2025-01-22 ～ 2025-01-24
**ステータス**: Phase 1 完了

Python Flow Editorの実装により、ユーザーはUIでPythonコードを直接編集してカスタムキャリブレーションワークフローを作成できるようになりました。

---

## 実装された機能

### 1. Core Infrastructure (✅ 完了)

#### FlowSession (`src/qdash/workflow/helpers/flow_helpers.py`)

- **自動execution_id生成**: YYYYMMDD-NNN形式
- **ExecutionLock管理**: 重複実行防止
- **ディレクトリ自動作成**: calibration data保存先
- **ChipHistory更新**: 完了時に自動更新
- **エラーハンドリング**: `fail_calibration()`メソッド

#### execute_task() メソッド

- **task_details対応**: パラメータのカスタマイズ
- **upstream_id対応**: qidごとのタスク依存関係追跡
- **戻り値にtask_id追加**: グループ実行での依存関係管理
- **統合保存処理**: TaskManagerとの連携

#### Helper Functions

- `init_calibration()` - セッション初期化
- `finish_calibration()` - セッション終了
- `get_session()` - 現在のセッション取得
- `calibrate_qubits_task_first()` - Task → Qubit順の実行
- `calibrate_qubits_qubit_first()` - Qubit → Task順の実行
- `adaptive_calibrate()` - 収束検出付き反復実行
- `execute_schedule()` - Schedule定義に基づく実行

### 2. UI Implementation (✅ 完了)

#### Flow List Page (`/flow`)

- Flowリスト表示
- 検索・フィルタリング
- 新規作成ボタン
- クリックで編集ページへ遷移

#### New Flow Page (`/flow/new`)

- テンプレート選択（7種類）
- Monaco Editorでのコード編集
- メタデータ編集（名前、説明、タグ等）
- **自動パラメータ補完**:
  - username: ログインユーザーから取得
  - chip_id: 最新チップから取得
- 保存機能

#### Edit Flow Page (`/flow/[name]`)

- コード編集（Monaco Editor）
- メタデータ編集
- **実行ロック機構**:
  - ExecutionLockStatus取得（5秒ごとにポーリング）
  - ロック中は"🔒 Locked"表示
  - 重複実行防止
- 削除機能
- toast通知（react-toastify）

#### API Endpoints

- `POST /flow/save` - Flow保存
- `GET /flow/{name}` - Flow取得
- `GET /flow/list` - Flowリスト取得
- `DELETE /flow/{name}` - Flow削除
- `POST /flow/execute` - Flow実行
- `GET /flow/templates` - テンプレートリスト取得
- `GET /flow/template/{id}` - テンプレート取得

### 3. Templates (✅ 完了)

#### Basic Templates

1. **Simple Flow** (`simple_flow.py`)
   - 基本的な単一キュービット校正
   - Prefect logger統合
   - デフォルトパラメータ

2. **Parallel Flow** (`parallel_flow.py`)
   - Task-first順序実行
   - 複数キュービットに並列的にタスク適用

3. **Sequential Flow** (`sequential_flow.py`)
   - Qubit-first順序実行
   - 各キュービットで全タスクを完了

#### Advanced Templates

4. **Custom Parallel Flow** (`custom_parallel_flow.py`) ⭐ NEW
   - グループ並列実行
   - upstream_id引き継ぎ
   - エラーハンドリング（失敗キュービットをスキップ）
   - 例: Group1(33→32) || Group2(36→38)

5. **Adaptive Flow** (`adaptive_flow.py`)
   - 収束検出
   - max_iterations制限
   - convergence_threshold設定

6. **Schedule Flow** (`schedule_flow.py`)
   - SerialNode/ParallelNode/BatchNode
   - 複雑なオーケストレーション

7. **Iterative Parallel Flow** (`iterative_flow.py`) ⭐ NEW
   - 並列グループ校正をN回繰り返し
   - 各イテレーションで異なるパラメータ注入可能
   - 安定性テスト・データ収集に最適
   - 例: 3回繰り返し、各回でdetune_frequencyを変更

### 4. Task Parameter Customization (✅ 完了)

#### CheckRabi修正 (`check_rabi.py`)

```python
def preprocess(self, session, qid):
    super().preprocess(session, qid)

    # Only set to 0 if no value was explicitly provided via task_details
    if self.input_parameters["detune_frequency"].value is None:
        self.input_parameters["detune_frequency"].value = 0

    return PreProcessResult(input_parameters=self.input_parameters)
```

**変更理由**: `task_details`で指定されたパラメータを上書きしないようにする

**影響**: すべてのタスクで同様のパターンが適用可能

---

## アーキテクチャ

### データフロー

```
User (UI)
  ↓
POST /flow/execute
  ↓
execute_flow() (api/flow.py)
  ↓
動的importでFlowモジュールをロード
  ↓
Prefect Flow実行
  ↓
FlowSession.execute_task()
  ↓
TaskManager.execute_task()
  ↓
BaseTask (run/preprocess/postprocess)
  ↓
保存処理（統合済み）
  ↓
ExecutionHistory / TaskResultHistory
```

### ファイル保存

```
/app/flows/{username}/{flow_name}.py  # Flowファイル
/app/calib_data/{username}/{date}/{index}/  # 校正データ
  ├── task/          # タスク結果JSON
  ├── fig/           # 図表
  ├── calib/         # 校正パラメータ
  └── calib_note/    # ノート
```

### MongoDB Documents

- **FlowDocument**: Flow定義（メタデータ + file_path）
- **ExecutionHistoryDocument**: 実行履歴
- **TaskResultHistoryDocument**: タスク結果履歴
- **ExecutionLockDocument**: 実行ロック状態
- **ExecutionCounterDocument**: execution_id用カウンター

---

## 主要な技術的決定

### 1. upstream_id管理

**問題**: 並列実行時に他のグループのtask_idで上書きされる

**解決策**: qidごとにupstream_idを記録

```python
# Before
self._last_executed_task_id = task_id  # ❌ 全体で共有

# After
self._last_executed_task_id_by_qid[qid] = task_id  # ✅ qidごと
```

### 2. task_detailsフォーマット

**正しいフォーマット**:

```python
{
    "CheckRabi": {
        "input_parameters": {
            "detune_frequency": {"value": 5.0}
        }
    }
}
```

**理由**: `BaseTask._convert_and_set_parameters()`が期待する構造

### 3. ExecutionCounter Race Condition

**問題**: 複数プロセスでの同時カウンター更新

**解決策**: リトライロジック + exponential backoff

```python
for attempt in range(max_retries):
    try:
        # Atomic increment
        result = collection.find_one_and_update(
            {"date": date, "username": username, "chip_id": chip_id},
            {"$inc": {"index": 1}},
            return_document=ReturnDocument.AFTER,
        )
        return result["index"]
    except DuplicateKeyError:
        time.sleep(0.01 * (attempt + 1))
```

### 4. 並列実行 vs execute_schedule

**発見**: `execute_schedule()`は`ParallelNode`でも順次実行

**理由**: Python Flow Editor内での実装のため

**解決策**: 真の並列実行には`.submit()`を使用

```python
# ❌ 順次実行
execute_schedule(tasks, ParallelNode(parallel=["0", "1"]))

# ✅ 並列実行
future1 = task.submit(args1)
future2 = task.submit(args2)
```

---

## パフォーマンス

### 並列実行の効果

- **Custom Parallel Flow**: 2グループ並列で約2倍高速化
- **Iterative Parallel Flow**: グループ並列により各イテレーションが高速化

### メモリ使用

- 各`execute_task`で新しいTaskManagerインスタンスを作成
- Task Result Historyに個別に記録
- 大量のイテレーションでもメモリリークなし

---

## 今後の拡張可能性

### 未実装機能（dispatch-closed-loop-implementation.md参照）

1. **Deployment経由のClosed Loop**
   - Python FlowをDeploymentとして登録
   - Menu systemからの呼び出し
   - 汎用的なループロジック

2. **UI拡張**
   - Flowのバージョン管理
   - 実行履歴の可視化
   - パラメータプリセット管理

3. **高度なパターン**
   - 動的なグループ生成
   - 条件分岐に基づくタスク選択
   - マルチレベルの並列実行

---

## 学んだ教訓

1. **段階的な機能追加**: SimpleからAdvancedへの明確なパス
2. **テンプレート駆動開発**: ユーザーは既存コードから学習
3. **明示的なAPI設計**: `task_first` vs `qubit_first`のような明確な命名
4. **エラーハンドリングの重要性**: グループ実行での失敗時の継続
5. **ドキュメントの重要性**: コード内コメントとTODOマーカー

---

## まとめ

Python Flow Editorの実装により、QDashは静的なMenu systemからPython記述可能な柔軟なワークフローシステムへと進化しました。

**主な成果**:

- ✅ 7種類のテンプレート
- ✅ UI完全統合（Monaco Editor）
- ✅ 並列・適応的・反復実行のサポート
- ✅ タスクパラメータのカスタマイズ
- ✅ 実行ロック機構
- ✅ エラーハンドリング

**次のステップ**: dispatch-closed-loop-implementationの実装検討
