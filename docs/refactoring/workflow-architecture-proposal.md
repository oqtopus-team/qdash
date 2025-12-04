# Workflow Architecture Refactoring Proposal

## Executive Summary

現在のワークフロークラス（`TaskManager`, `ExecutionManager`, `FlowSession`）は単一責任原則（SRP）に違反しており、テストが困難な設計になっています。本ドキュメントでは、依存性注入とレイヤード・アーキテクチャを導入することで、テスタビリティと保守性を向上させるリファクタリング案を提案します。

---

## 1. 現状分析

### 1.1 TaskManager (`src/qdash/workflow/engine/calibration/task_manager.py`)

**ファイル規模:** 約750行

**現在担っている責任:**

| 責任                           | メソッド例                                                        | 問題点               |
| ------------------------------ | ----------------------------------------------------------------- | -------------------- |
| タスク状態管理                 | `start_task()`, `end_task()`, `update_task_status()`              | 適切                 |
| 図の保存                       | `save_figures()`, `_write_figure_json()`, `_write_figure_image()` | ファイルI/O直接実行  |
| 生データ保存                   | `save_raw_data()`                                                 | ファイルI/O直接実行  |
| タスク実行オーケストレーション | `execute_task()`                                                  | 複数の責任を内包     |
| パラメータ管理                 | `put_input_parameters()`, `put_output_parameters()`               | 適切                 |
| データベース更新               | `TaskResultHistoryDocument.upsert_document()`                     | DB直接呼び出し       |
| バックエンド固有処理           | `_save_qubex_specific()`, `_save_fake_specific()`                 | 条件分岐が肥大化     |
| R²検証ロジック                 | `_save_all_results()` 内                                          | ビジネスロジック混在 |

**SRP違反の具体例:**

```python
# execute_task() メソッド内で以下を全て実行
def execute_task(self, task_instance, session, execution_manager, qid):
    # 1. タスク存在確認・追加
    self._ensure_task_exists(task_name, task_type, qid)

    # 2. タスク開始処理
    self.start_task(task_name, task_type, qid)

    # 3. DBへの状態保存
    TaskResultHistoryDocument.upsert_document(...)  # 直接DB呼び出し

    # 4. プリプロセス実行
    preprocess_result = task_instance.preprocess(session, qid)

    # 5. メイン処理実行
    run_result = task_instance.run(session, qid)

    # 6. ポストプロセス実行
    postprocess_result = task_instance.postprocess(...)

    # 7. 結果保存（図、生データ、パラメータ）
    self._save_all_results(...)

    # 8. ChipHistoryの更新
    ChipHistoryDocument.create_history(chip_doc)  # 直接DB呼び出し
```

> **重要:** `TaskExecutor` 側でR²/フィデリティ検証が完了するまでは `save_output_parameters` / `save_figures` / `save_raw_data` を呼び出さない。これにより閾値未達の結果が Mongo / ファイルシステムに永続化されることを防ぎ、現行 `_save_all_results()` と同じ安全性を担保する。

**テスト困難性:**

- `Pydantic.BaseModel`を継承しつつ巨大なビジネスロジックを持つ
- DBモデル（`TaskResultHistoryDocument`, `QubitDocument`, `CouplingDocument`）を直接呼び出し
- ファイルI/Oを直接実行（`Path.mkdir()`, `fig.write_image()`）
- テスト時に実データベースと実ファイルシステムが必要

---

### 1.2 ExecutionManager (`src/qdash/workflow/engine/calibration/execution_manager.py`)

**ファイル規模:** 約250行

**現在担っている責任:**

| 責任                      | メソッド例                                                     | 問題点                      |
| ------------------------- | -------------------------------------------------------------- | --------------------------- |
| 実行状態管理              | `update_status()`, `start_execution()`, `complete_execution()` | 適切                        |
| MongoDB直接操作           | `_with_db_transaction()`                                       | PyMongoクライアント直接生成 |
| タイムスタンプ計算        | `calculate_elapsed_time()`                                     | 適切                        |
| TaskManagerとのデータ同期 | `update_with_task_manager()`                                   | 複雑なマージロジック        |

**SRP違反の具体例:**

```python
def _with_db_transaction(self, func):
    # メソッド内でMongoClientを直接生成
    client: MongoClient = MongoClient(
        "mongo",
        port=27017,
        username=os.getenv("MONGO_INITDB_ROOT_USERNAME"),
        password=os.getenv("MONGO_INITDB_ROOT_PASSWORD"),
    )
    collection = client.qubex[ExecutionHistoryDocument.Settings.name]

    # 楽観ロックロジックも埋め込み
    while True:
        result = collection.find_one_and_update(
            {"execution_id": self.execution_id, "$or": [...]},
            {..., "$inc": {"_version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if result is not None:
            break
```

**テスト困難性:**

- `MongoClient`をメソッド内で直接生成 → モック不可能
- 環境変数への直接依存
- 楽観ロックロジックが埋め込まれている

---

### 1.3 FlowSession (`src/qdash/workflow/flow/session.py`)

**ファイル規模:** 約650行

**現在担っている責任:**

| 責任                              | メソッド例                                                 | 問題点           |
| --------------------------------- | ---------------------------------------------------------- | ---------------- |
| セッションライフサイクル管理      | `__init__()`, `finish_calibration()`, `fail_calibration()` | `__init__`が巨大 |
| ディレクトリ作成                  | `__init__`内                                               | 副作用が多い     |
| ExecutionLock取得/解放            | `__init__`内, `finish_calibration()`                       | 適切             |
| GitHub連携                        | `__init__`内, `finish_calibration()`                       | 責任過多         |
| TaskManager/ExecutionManager生成  | `__init__`内                                               | ファクトリー責任 |
| Prefectグローバルコンテキスト管理 | `_current_session` グローバル変数                          | テスト困難       |

**SRP違反の具体例:**

```python
def __init__(self, username, chip_id, qids, ...):
    # 1. ロック取得
    if use_lock:
        ExecutionLockDocument.lock()

    # 2. ディレクトリ作成（副作用）
    Path(calib_data_path).mkdir(parents=True, exist_ok=True)
    Path(classifier_dir).mkdir(exist_ok=True)
    # ... 複数のmkdir

    # 3. GitHub pull（外部API呼び出し）
    if enable_github_pull:
        commit_id = self.github_integration.pull_config()

    # 4. ExecutionManager生成・保存・状態更新
    self.execution_manager = (
        ExecutionManager(...)
        .save()
        .start_execution()
        .update_execution_status_to_running()
    )

    # 5. TaskManager生成
    self.task_manager = TaskManager(...)

    # 6. セッション生成・接続
    self.session = create_backend(...)
    self.session.connect()
```

**テスト困難性:**

- `__init__`で多数の副作用が発生
- グローバル変数 `_current_session` の使用
- 外部サービス（GitHub、MongoDB）への依存

---

## 2. 提案アーキテクチャ

### 2.1 レイヤード・アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                      Application Layer                           │
│  FlowSession (thin facade/coordinator)                          │
│  - セッションのエントリーポイント                                  │
│  - 薄いファサードとして各サービスを調整                            │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ TaskStateManager │ │ ResultPersister  │ │ExecutionService  │
│ (Pure Logic)     │ │ (Save Operations)│ │ (Execution State)│
│                  │ │                  │ │                  │
│ - 状態遷移のみ    │ │ - 図の保存       │ │ - 実行状態管理    │
│ - 副作用なし      │ │ - 生データ保存   │ │ - ステータス更新  │
│ - テスト容易      │ │ - パラメータ保存 │ │                  │
└──────────────────┘ └──────────────────┘ └──────────────────┘
          │                   │                   │
          └───────────────────┼───────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Repository Layer                            │
│  TaskRepository, ExecutionRepository, FigureRepository          │
│  - データアクセスの抽象化                                         │
│  - インターフェース定義による依存性逆転                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Infrastructure Adapters                        │
│  MongoAdapter, FileSystemAdapter, BackendAdapter                │
│  - 具体的な永続化実装                                            │
│  - テスト用のインメモリ実装も提供                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 依存性の方向

```
Application Layer
       │
       │ depends on (interface)
       ▼
Domain Layer (Interfaces/Protocols)
       ▲
       │ implements
       │
Infrastructure Layer
```

---

## 3. 詳細設計

### 3.1 Repository Layer - インターフェース定義

```python
# src/qdash/workflow/engine/repositories/protocols.py

from typing import Protocol, Any
from pathlib import Path
from qdash.datamodel.task import TaskResultModel, BaseTaskResultModel
from qdash.datamodel.execution import ExecutionModel

class TaskRepository(Protocol):
    """タスク結果の永続化インターフェース"""

    def save_task_result(
        self,
        task_id: str,
        result: BaseTaskResultModel,
        execution_id: str,
    ) -> None:
        """タスク結果を保存"""
        ...

    def get_task_result(
        self,
        task_id: str,
    ) -> BaseTaskResultModel | None:
        """タスク結果を取得"""
        ...

    def upsert_task_history(
        self,
        task: BaseTaskResultModel,
        execution_model: ExecutionModel,
    ) -> None:
        """タスク履歴をupsert"""
        ...


class ExecutionRepository(Protocol):
    """実行状態の永続化インターフェース"""

    def save(self, execution: ExecutionModel) -> None:
        """実行状態を保存"""
        ...

    def find_by_id(self, execution_id: str) -> ExecutionModel | None:
        """実行状態を取得"""
        ...

    def update_status(
        self,
        execution_id: str,
        status: str,
        additional_fields: dict[str, Any] | None = None,
    ) -> None:
        """ステータスを更新"""
        ...


class FigurePersister(Protocol):
    """図・生データの永続化インターフェース"""

    def save_figures(
        self,
        figures: list,
        base_path: Path,
        task_name: str,
        qid: str,
    ) -> tuple[list[str], list[str]]:
        """図を保存し、(png_paths, json_paths)を返す"""
        ...

    def save_raw_data(
        self,
        data: list,
        base_path: Path,
        task_name: str,
        qid: str,
    ) -> list[str]:
        """生データを保存し、pathリストを返す"""
        ...


class CalibDataRepository(Protocol):
    """キャリブレーションデータの永続化インターフェース"""

    def update_qubit_calib_data(
        self,
        username: str,
        qid: str,
        chip_id: str,
        output_parameters: dict[str, Any],
    ) -> None:
        """Qubitキャリブレーションデータを更新"""
        ...

    def update_coupling_calib_data(
        self,
        username: str,
        qid: str,
        chip_id: str,
        output_parameters: dict[str, Any],
    ) -> None:
        """Couplingキャリブレーションデータを更新"""
        ...
```

### 3.2 Repository Layer - 本番実装

```python
# src/qdash/workflow/engine/repositories/mongo.py

from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.coupling import CouplingDocument

class MongoTaskRepository:
    """MongoDB実装"""

    def save_task_result(self, task_id: str, result, execution_id: str) -> None:
        # 既存のTaskResultHistoryDocument.upsert_documentを呼び出し
        ...

    def upsert_task_history(self, task, execution_model) -> None:
        TaskResultHistoryDocument.upsert_document(task=task, execution_model=execution_model)


class MongoExecutionRepository:
    """MongoDB実装"""

    def __init__(self, client=None):
        # 外部から注入可能なMongoClient
        self._client = client

    def save(self, execution: ExecutionModel) -> None:
        ExecutionHistoryDocument.upsert_document(execution)

    def find_by_id(self, execution_id: str) -> ExecutionModel | None:
        doc = ExecutionHistoryDocument.find_one({"execution_id": execution_id}).run()
        return ExecutionModel.model_validate(doc.model_dump()) if doc else None


class MongoCalibDataRepository:
    """MongoDB実装"""

    def update_qubit_calib_data(self, username, qid, chip_id, output_parameters) -> None:
        QubitDocument.update_calib_data(
            username=username,
            qid=qid,
            chip_id=chip_id,
            output_parameters=output_parameters,
        )

    def update_coupling_calib_data(self, username, qid, chip_id, output_parameters) -> None:
        CouplingDocument.update_calib_data(
            username=username,
            qid=qid,
            chip_id=chip_id,
            output_parameters=output_parameters,
        )
```

### 3.3 Repository Layer - テスト方針

実環境と挙動差が出ないよう、リファクタ後のテストも Docker 内 Mongo コンテナに `qubex_test` DB を追加して実 DB 経由で実施する。インメモリ実装は用意せず、本番と同じ永続化コードを通す。

### 3.4 TaskManagerの分割

#### 3.4.1 TaskStateManager（純粋な状態管理）

```python
# src/qdash/workflow/engine/calibration/task_state_manager.py

from pydantic import BaseModel
from qdash.datamodel.task import CalibDataModel, TaskResultModel, TaskStatusModel
import pendulum

class TaskStateManager(BaseModel):
    """タスクの状態遷移を管理（副作用なし）"""

    task_result: TaskResultModel
    calib_data: CalibDataModel
    controller_info: dict[str, dict] = {}

    def start_task(self, task_name: str, task_type: str, qid: str) -> None:
        """タスクを開始状態にする"""
        container = self._get_task_container(task_type, qid)
        for t in container:
            if t.name == task_name:
                t.status = TaskStatusModel.RUNNING
                t.message = f"{task_name} is running."
                t.start_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
                t.system_info.update_time()
                return
        raise ValueError(f"Task '{task_name}' not found in container.")

    def complete_task(self, task_name: str, task_type: str, qid: str, message: str = "") -> None:
        """タスクを完了状態にする"""
        self._update_status(task_name, TaskStatusModel.COMPLETED, message, task_type, qid)

    def fail_task(self, task_name: str, task_type: str, qid: str, message: str = "") -> None:
        """タスクを失敗状態にする"""
        self._update_status(task_name, TaskStatusModel.FAILED, message, task_type, qid)

    def end_task(self, task_name: str, task_type: str, qid: str) -> None:
        """タスクの終了時刻を記録"""
        container = self._get_task_container(task_type, qid)
        for t in container:
            if t.name == task_name:
                t.end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
                t.elapsed_time = t.calculate_elapsed_time(t.start_at, t.end_at)
                t.system_info.update_time()
                return

    def ensure_task_exists(self, task_name: str, task_type: str, qid: str) -> None:
        """タスクが存在しなければ追加"""
        # 既存の_ensure_task_existsロジック
        ...

    def put_input_parameters(self, task_name: str, params: dict, task_type: str, qid: str) -> None:
        """入力パラメータを設定"""
        task = self._find_task(task_name, task_type, qid)
        task.put_input_parameter(params)
        task.system_info.update_time()

    def put_output_parameters(self, task_name: str, params: dict, task_type: str, qid: str) -> None:
        """出力パラメータを設定"""
        task = self._find_task(task_name, task_type, qid)
        task.put_output_parameter(params)
        task.system_info.update_time()

    def clear_output_parameters(self, task_name: str, task_type: str, qid: str) -> None:
        """R²等で失敗した場合に出力を巻き戻す"""
        task = self._find_task(task_name, task_type, qid)
        task.output_parameters.clear()
        task.system_info.update_time()

    def get_task(self, task_name: str, task_type: str, qid: str) -> BaseTaskResultModel:
        """タスクを取得"""
        return self._find_task(task_name, task_type, qid)

    # 内部メソッド
    def _get_task_container(self, task_type: str, qid: str):
        # 既存ロジック
        ...

    def _find_task(self, task_name: str, task_type: str, qid: str):
        # 既存ロジック
        ...

    def _update_status(self, task_name, status, message, task_type, qid):
        # 既存ロジック
        ...
```

#### 3.4.2 TaskResultProcessor（結果保存処理）

```python
# src/qdash/workflow/engine/calibration/task_result_processor.py

from typing import Any
from pathlib import Path
from qdash.workflow.engine.repositories.protocols import (
    TaskRepository,
    FigurePersister,
    CalibDataRepository,
)

class TaskResultProcessor:
    """タスク実行結果の保存処理"""

    def __init__(
        self,
        task_repository: TaskRepository,
        figure_persister: FigurePersister,
        calib_data_repository: CalibDataRepository,
        calib_dir: str,
    ):
        self._task_repository = task_repository
        self._figure_persister = figure_persister
        self._calib_data_repository = calib_data_repository
        self._calib_dir = calib_dir

    def save_task_state(
        self,
        task: BaseTaskResultModel,
        execution_model: ExecutionModel,
    ) -> None:
        """タスク状態をDBに保存"""
        self._task_repository.upsert_task_history(task, execution_model)

    def save_output_parameters(
        self,
        username: str,
        qid: str,
        chip_id: str,
        task_type: str,
        output_parameters: dict[str, Any],
    ) -> None:
        """出力パラメータをDBに保存"""
        if task_type == "qubit":
            self._calib_data_repository.update_qubit_calib_data(
                username, qid, chip_id, output_parameters
            )
        elif task_type == "coupling":
            self._calib_data_repository.update_coupling_calib_data(
                username, qid, chip_id, output_parameters
            )

    def save_figures(
        self,
        figures: list,
        task_name: str,
        qid: str,
    ) -> tuple[list[str], list[str]]:
        """図を保存"""
        base_path = Path(self._calib_dir) / "fig"
        return self._figure_persister.save_figures(figures, base_path, task_name, qid)

    def save_raw_data(
        self,
        raw_data: list,
        task_name: str,
        qid: str,
    ) -> list[str]:
        """生データを保存"""
        base_path = Path(self._calib_dir) / "raw_data"
        return self._figure_persister.save_raw_data(raw_data, base_path, task_name, qid)
```

#### 3.4.3 TaskHistoryRecorder（履歴スナップショット）

```python
# src/qdash/workflow/engine/calibration/task_history_recorder.py

from qdash.workflow.engine.repositories.protocols import TaskRepository

class TaskHistoryRecorder:
    """TaskResultHistoryDocument相当のスナップショット管理"""

    def __init__(self, repository: TaskRepository):
        self._repository = repository

    def snapshot(self, task: BaseTaskResultModel, execution: ExecutionModel) -> None:
        """TaskManager状態をMongoに保存"""
        self._repository.upsert_task_history(task, execution)
```

> **補足:** `TaskExecutor` は開始時・完了時・finally ブロックで `TaskHistoryRecorder.snapshot()` を呼び出し、現行 `TaskManager.execute_task()` が担っていた `TaskResultHistoryDocument.upsert_document()` と同じイベント順を維持する。

#### 3.4.4 ValidationService（検証ロジック）

```python
# src/qdash/workflow/engine/calibration/validation_service.py

from typing import Any

class ValidationService:
    """タスク結果の検証ロジック"""

    def validate_r2(
        self,
        run_result: Any,
        qid: str,
        threshold: float,
    ) -> tuple[bool, float | None]:
        """R²値を検証

        Returns:
            (is_valid, r2_value): 検証結果とR²値
        """
        if not run_result.has_r2():
            return True, None  # R²がない場合はパス

        r2_value = run_result.r2.get(qid)
        if r2_value is None:
            return False, None

        if r2_value < threshold:
            return False, r2_value

        return True, r2_value

    def validate_fidelity(
        self,
        output_parameters: dict[str, Any],
        task_name: str,
    ) -> None:
        """Fidelity値を検証（RBタスク用）

        Raises:
            ValueError: Fidelityが1.0を超える場合
        """
        is_rb_task = "randomized" in task_name.lower() or "benchmarking" in task_name.lower()
        if not is_rb_task:
            return

        for param_name, param_value in output_parameters.items():
            if "fidelity" in param_name.lower():
                fidelity = param_value.value
                if fidelity is not None and fidelity > 1.0:
                    raise ValueError(
                        f"{task_name} failed: {param_name} = {fidelity:.4f} "
                        f"exceeds 100% (physical maximum is 1.0)"
                    )
```

#### 3.4.5 TaskExecutor（オーケストレーター）

> QDash のモデル群と整合を保つため、`TaskExecutionResult` や関連 DTO も `pydantic.BaseModel` で定義し、シリアライズや Prefect 間の値受け渡しを統一する。

```python
# src/qdash/workflow/engine/calibration/task_executor.py

from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from qdash.workflow.tasks.base import BaseTask
    from qdash.workflow.engine.backend.base import BaseBackend

class TaskExecutionResult(BaseModel):
    task: BaseTaskResultModel
    output_parameters: dict[str, Any]
    calib_data_delta: CalibDataModel
    controller_info: dict[str, dict] = Field(default_factory=dict)


class TaskExecutor:
    """タスク実行の調整（薄いオーケストレーター）"""

    def __init__(
        self,
        state_manager: TaskStateManager,
        result_processor: TaskResultProcessor,
        validation_service: ValidationService,
        history_recorder: TaskHistoryRecorder,
        backend_updater: BackendParamsUpdater | None = None,
    ):
        self._state_manager = state_manager
        self._result_processor = result_processor
        self._validation_service = validation_service
        self._history_recorder = history_recorder
        self._backend_updater = backend_updater

    def execute(
        self,
        task_instance: "BaseTask",
        session: "BaseBackend",
        execution_model: ExecutionModel,
        qid: str,
        username: str,
    ) -> dict[str, Any]:
        """タスクを実行し結果を返す"""
        task_name = task_instance.get_name()
        task_type = task_instance.get_task_type()

        try:
            # 1. タスク存在確認
            self._state_manager.ensure_task_exists(task_name, task_type, qid)

            # 2. 開始
            self._state_manager.start_task(task_name, task_type, qid)
            self._history_recorder.snapshot(
                self._state_manager.get_task(task_name, task_type, qid),
                execution_model,
            )

            # 3. プリプロセス
            preprocess_result = task_instance.preprocess(session, qid)
            if preprocess_result:
                self._state_manager.put_input_parameters(
                    task_name, preprocess_result.input_parameters, task_type, qid
                )

            # 4. 実行
            run_result = task_instance.run(session, qid)

            # 5. ポストプロセス
            if run_result:
                postprocess_result = task_instance.postprocess(
                    session, execution_model.execution_id, run_result, qid
                )

                if postprocess_result:
                    self._process_results(
                        task_instance, execution_model, postprocess_result,
                        qid, run_result, session, username
                    )

            # 6. 完了
            self._state_manager.complete_task(
                task_name, f"{task_name} is completed", task_type, qid
            )

        except Exception as e:
            self._state_manager.fail_task(task_name, str(e), task_type, qid)
            raise

        finally:
            self._state_manager.end_task(task_name, task_type, qid)
            self._history_recorder.snapshot(
                self._state_manager.get_task(task_name, task_type, qid),
                execution_model,
            )

        task_model = self._state_manager.get_task(task_name, task_type, qid)
        return TaskExecutionResult(
            task=task_model,
            output_parameters=dict(task_model.output_parameters),
            calib_data_delta=self._state_manager.calib_data,
            controller_info=self._state_manager.controller_info,
        )

    def _process_results(self, task_instance, execution_model, postprocess_result, qid, run_result, session, username):
        """結果の処理と保存"""
        task_name = task_instance.get_name()
        task_type = task_instance.get_task_type()

        # Fidelity検証
        if postprocess_result.output_parameters:
            self._validation_service.validate_fidelity(
                postprocess_result.output_parameters, task_name
            )

        # 出力パラメータ保存
        if postprocess_result.output_parameters:
            self._state_manager.put_output_parameters(
                task_name, postprocess_result.output_parameters, task_type, qid
            )

        # 図の保存
        if postprocess_result.figures:
            pending_figures = postprocess_result.figures
        else:
            pending_figures = []

        # 生データ保存
        if postprocess_result.raw_data:
            pending_raw_data = postprocess_result.raw_data
        else:
            pending_raw_data = []

        # R²検証
        is_valid, r2_value = self._validation_service.validate_r2(
            run_result, qid, task_instance.r2_threshold
        )
        if not is_valid and r2_value is not None:
            self._state_manager.clear_output_parameters(task_name, task_type, qid)
            raise ValueError(f"{task_name} R² value too low: {r2_value:.4f}")

        # ここで初めて副作用を実行
        if postprocess_result.output_parameters:
            self._result_processor.save_output_parameters(
                username, qid, execution_model.chip_id, task_type,
                postprocess_result.output_parameters
            )
        if pending_figures:
            png_paths, json_paths = self._result_processor.save_figures(
                pending_figures, task_name, qid
            )
            task = self._state_manager.get_task(task_name, task_type, qid)
            task.figure_path = png_paths
            task.json_figure_path = json_paths
        if pending_raw_data:
            paths = self._result_processor.save_raw_data(
                pending_raw_data, task_name, qid
            )
            task = self._state_manager.get_task(task_name, task_type, qid)
            task.raw_data_path = paths

        # バックエンドパラメータ/ノート更新
        if self._backend_updater:
            self._backend_updater.update(
                session=session,
                execution_model=execution_model,
                task_name=task_name,
                task_type=task_type,
                qid=qid,
                output_parameters=postprocess_result.output_parameters,
            )
```

> `BackendParamsUpdater` は `session.update_note()`、`get_params_updater()`、ChipHistory などの既存副作用を集約し、バックエンドごとに差し替え可能な境界とする。

### 3.5 ExecutionManagerの改善

```python
# src/qdash/workflow/engine/calibration/execution_state_manager.py

from pydantic import BaseModel
import pendulum
from qdash.datamodel.execution import ExecutionModel, ExecutionStatusModel

class ExecutionStateManager(BaseModel):
    """実行状態管理（純粋なロジック、DB依存なし）"""

    execution: ExecutionModel

    def start(self) -> "ExecutionStateManager":
        """実行を開始状態にする"""
        self.execution.start_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        self.execution.status = ExecutionStatusModel.RUNNING
        return self

    def complete(self) -> "ExecutionStateManager":
        """実行を完了状態にする"""
        end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        self.execution.end_at = end_at
        self.execution.elapsed_time = self._calculate_elapsed_time(
            self.execution.start_at, end_at
        )
        self.execution.status = ExecutionStatusModel.COMPLETED
        return self

    def fail(self) -> "ExecutionStateManager":
        """実行を失敗状態にする"""
        end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        self.execution.end_at = end_at
        self.execution.elapsed_time = self._calculate_elapsed_time(
            self.execution.start_at, end_at
        )
        self.execution.status = ExecutionStatusModel.FAILED
        return self

    def merge_task_results(self, task_manager_id: str, task_result: TaskResultModel) -> None:
        """タスク結果をマージ"""
        self.execution.task_results[task_manager_id] = task_result

    def merge_calib_data(self, calib_data: CalibDataModel) -> None:
        """キャリブレーションデータをマージ"""
        for qid, data in calib_data.qubit.items():
            if qid not in self.execution.calib_data.qubit:
                self.execution.calib_data.qubit[qid] = {}
            self.execution.calib_data.qubit[qid].update(data)

        for qid, data in calib_data.coupling.items():
            if qid not in self.execution.calib_data.coupling:
                self.execution.calib_data.coupling[qid] = {}
            self.execution.calib_data.coupling[qid].update(data)

    def _calculate_elapsed_time(self, start_at: str, end_at: str) -> str:
        start_time = pendulum.parse(start_at)
        end_time = pendulum.parse(end_at)
        return end_time.diff_for_humans(start_time, absolute=True)


# src/qdash/workflow/engine/calibration/execution_service.py

class ExecutionService:
    """実行の永続化を含む操作"""

    def __init__(self, repository: ExecutionRepository):
        self._repository = repository

    def create(self, config: ExecutionConfig) -> ExecutionStateManager:
        """新規実行を作成"""
        execution = ExecutionModel(
            username=config.username,
            execution_id=config.execution_id,
            # ...
        )
        self._repository.save(execution)
        return ExecutionStateManager(execution=execution)

    def load(self, execution_id: str) -> ExecutionStateManager | None:
        """実行を読み込み"""
        execution = self._repository.find_by_id(execution_id)
        if execution is None:
            return None
        return ExecutionStateManager(execution=execution)

    def save(self, state_manager: ExecutionStateManager) -> None:
        """実行を保存"""
        self._repository.save(state_manager.execution)

    def start_execution(self, execution_id: str) -> ExecutionStateManager:
        """実行を開始"""
        state = self.load(execution_id)
        if state is None:
            raise ValueError(f"Execution {execution_id} not found")
        state.start()
        self.save(state)
        return state
```

### 3.6 FlowSessionの簡素化

```python
# src/qdash/workflow/flow/session_config.py

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class FlowSessionConfig:
    """FlowSessionの設定（値オブジェクト）"""
    username: str
    chip_id: str
    qids: list[str]
    execution_id: str | None = None
    backend: str = "qubex"
    name: str = "Python Flow Execution"
    tags: list[str] | None = None
    use_lock: bool = True
    note: dict[str, Any] | None = None
    muxes: list[int] | None = None


# src/qdash/workflow/flow/session_factory.py

class FlowSessionFactory:
    """FlowSessionのファクトリー"""

    @staticmethod
    def create(config: FlowSessionConfig) -> "FlowSession":
        """本番環境用のFlowSessionを生成"""
        # 依存性の生成
        execution_repository = MongoExecutionRepository()
        task_repository = MongoTaskRepository()
        calib_data_repository = MongoCalibDataRepository()
        figure_persister = LocalFilePersister()

        execution_service = ExecutionService(execution_repository)

        # ... 他の依存性

        return FlowSession(
            config=config,
            execution_service=execution_service,
            task_executor_factory=TaskExecutorFactory(
                task_repository=task_repository,
                figure_persister=figure_persister,
                calib_data_repository=calib_data_repository,
            ),
            lock_service=ExecutionLockService(),
            directory_service=DirectoryService(),
        )

    @staticmethod
    def create_for_test(
        config: FlowSessionConfig,
        execution_repository: ExecutionRepository | None = None,
        task_repository: TaskRepository | None = None,
    ) -> "FlowSession":
        """テスト用のFlowSessionを生成"""
        # テスト環境でも Mongo (qubex_test) を利用し、本番と同じリポジトリを使用する
        execution_repository = execution_repository or MongoExecutionRepository(test_client)
        task_repository = task_repository or MongoTaskRepository()
        figure_persister = LocalFilePersister()
        calib_data_repository = MongoCalibDataRepository()

        return FlowSession(...)


# src/qdash/workflow/flow/session_state.py

from pydantic import BaseModel, Field
from qdash.datamodel.task import CalibDataModel, TaskResultModel
from qdash.workflow.engine.calibration.task_executor import TaskExecutionResult

class SessionStateStore(BaseModel):
    """Prefect セッション間で TaskManager 相当の情報を集約"""

    calib_data: CalibDataModel = Field(default_factory=lambda: CalibDataModel(qubit={}, coupling={}))
    controller_info: dict[str, dict] = Field(default_factory=dict)
    task_results: dict[str, TaskResultModel] = Field(default_factory=dict)

    def merge(self, manager_id: str, result: TaskExecutionResult) -> None:
        self.task_results[manager_id] = result.task
        for qid, params in result.calib_data_delta.qubit.items():
            self.calib_data.qubit.setdefault(qid, {}).update(params)
        for qid, params in result.calib_data_delta.coupling.items():
            self.calib_data.coupling.setdefault(qid, {}).update(params)
        self.controller_info.update(result.controller_info)

    def get_parameter(self, qid: str, param_name: str) -> Any:
        return self.calib_data.qubit.get(qid, {}).get(param_name)

> FlowSession は `SessionStateStore` を介して UI 向けのパラメータ問い合わせや `ExecutionService` への最終保存データを取得する。


# src/qdash/workflow/flow/session.py (リファクタリング後)

class FlowSession:
    """薄いファサード - 各サービスを調整するのみ"""

    def __init__(
        self,
        config: FlowSessionConfig,
        execution_service: ExecutionService,
        task_executor_factory: TaskExecutorFactory,
        lock_service: LockService,
        directory_service: DirectoryService,
        github_integration: GitHubIntegration | None = None,
        state_store: SessionStateStore | None = None,
    ):
        self._config = config
        self._execution_service = execution_service
        self._task_executor_factory = task_executor_factory
        self._lock_service = lock_service
        self._directory_service = directory_service
        self._github_integration = github_integration
        self._state_store = state_store or SessionStateStore()

        self._execution_state: ExecutionStateManager | None = None
        self._lock_acquired = False

    def start(self) -> "FlowSession":
        """セッションを開始"""
        # ロック取得
        if self._config.use_lock:
            if self._lock_service.is_locked():
                raise RuntimeError("Calibration is already running")
            self._lock_service.acquire()
            self._lock_acquired = True

        # ディレクトリ作成
        self._directory_service.create_calibration_dirs(
            self._config.username,
            self._config.execution_id,
        )

        # 実行開始
        self._execution_state = self._execution_service.create(self._config)
        self._execution_state.start()
        self._execution_service.save(self._execution_state)

        return self

    def execute_task(self, task_name: str, qid: str) -> dict[str, Any]:
        """タスクを実行"""
        if self._execution_state is None:
            raise RuntimeError("Session not started")

        executor = self._task_executor_factory.create(
            execution_model=self._execution_state.execution,
            calib_dir=self._get_calib_dir(),
        )

        result = executor.execute(
            task_name=task_name,
            qid=qid,
            username=self._config.username,
        )
        self._state_store.merge(result.task.task_id, result)
        return result.output_parameters

    def finish(self) -> None:
        """セッションを終了"""
        try:
            if self._execution_state:
                self._execution_state.complete()
                self._execution_service.save(self._execution_state)
        finally:
            if self._lock_acquired:
                self._lock_service.release()
                self._lock_acquired = False

    def fail(self, error_message: str = "") -> None:
        """セッションを失敗で終了"""
        try:
            if self._execution_state:
                self._execution_state.fail()
                self._execution_service.save(self._execution_state)
        finally:
            if self._lock_acquired:
                self._lock_service.release()
                self._lock_acquired = False
```

> Prefect の `execute_dynamic_task_by_qid` / `execute_dynamic_task_batch` の戻り値として `TaskExecutionResult` を返し、FlowSession が `SessionStateStore.merge()` を呼ぶことで既存の Prefect 連携と互換性を保つ。

> `finish()` / `fail()` では `SessionStateStore` 内の `task_results` と `calib_data` を `ExecutionStateManager` にマージしてから `ExecutionService.save()` を呼び、Mongo に反映させる。

---

## 4. テスト例

### 4.1 TaskStateManagerのテスト

```python
# tests/qdash/workflow/engine/calibration/test_task_state_manager.py

import pytest
from qdash.datamodel.task import TaskResultModel, TaskStatusModel, QubitTaskModel
from qdash.workflow.engine.calibration.task_state_manager import TaskStateManager

class TestTaskStateManager:
    """TaskStateManagerの単体テスト（DB不要）"""

    def test_start_task_updates_status(self):
        # Arrange
        task_result = TaskResultModel()
        task_result.qubit_tasks["Q0"] = [
            QubitTaskModel(name="CheckFreq", qid="Q0")
        ]
        state_manager = TaskStateManager(task_result=task_result)

        # Act
        state_manager.start_task("CheckFreq", "qubit", "Q0")

        # Assert
        task = state_manager.get_task("CheckFreq", "qubit", "Q0")
        assert task.status == TaskStatusModel.RUNNING
        assert task.start_at != ""

    def test_complete_task_updates_status(self):
        # Arrange
        task_result = TaskResultModel()
        task_result.qubit_tasks["Q0"] = [
            QubitTaskModel(name="CheckFreq", qid="Q0")
        ]
        state_manager = TaskStateManager(task_result=task_result)
        state_manager.start_task("CheckFreq", "qubit", "Q0")

        # Act
        state_manager.complete_task("CheckFreq", "qubit", "Q0", "Success")

        # Assert
        task = state_manager.get_task("CheckFreq", "qubit", "Q0")
        assert task.status == TaskStatusModel.COMPLETED
        assert task.message == "Success"

    def test_fail_task_updates_status(self):
        # Arrange
        task_result = TaskResultModel()
        task_result.qubit_tasks["Q0"] = [
            QubitTaskModel(name="CheckFreq", qid="Q0")
        ]
        state_manager = TaskStateManager(task_result=task_result)
        state_manager.start_task("CheckFreq", "qubit", "Q0")

        # Act
        state_manager.fail_task("CheckFreq", "qubit", "Q0", "Error occurred")

        # Assert
        task = state_manager.get_task("CheckFreq", "qubit", "Q0")
        assert task.status == TaskStatusModel.FAILED
        assert task.message == "Error occurred"
```

### 4.2 TaskExecutorのテスト（モック使用）

```python
# tests/qdash/workflow/engine/calibration/test_task_executor.py

import pytest
from unittest.mock import Mock, MagicMock
from qdash.workflow.engine.calibration.task_executor import TaskExecutor
from qdash.workflow.engine.calibration.task_state_manager import TaskStateManager
from qdash.workflow.engine.calibration.task_result_processor import TaskResultProcessor
from qdash.workflow.engine.calibration.validation_service import ValidationService
from unittest.mock import MagicMock

class TestTaskExecutor:
    """TaskExecutorの単体テスト（実DB不要）"""

    @pytest.fixture
    def executor(self):
        state_manager = TaskStateManager(task_result=TaskResultModel())
        result_processor = TaskResultProcessor(
            task_repository=MagicMock(),
            figure_persister=MagicMock(),
            calib_data_repository=Mock(),
            calib_dir="/tmp/test",
        )
        validation_service = ValidationService()

        return TaskExecutor(
            state_manager=state_manager,
            result_processor=result_processor,
            validation_service=validation_service,
        )

    def test_execute_calls_task_lifecycle(self, executor):
        # Arrange
        mock_task = Mock()
        mock_task.get_name.return_value = "CheckFreq"
        mock_task.get_task_type.return_value = "qubit"
        mock_task.preprocess.return_value = None
        mock_task.run.return_value = Mock(has_r2=lambda: False)
        mock_task.postprocess.return_value = None

        mock_session = Mock()
        mock_execution = Mock(execution_id="test-001", chip_id="chip-1")

        # Act
        result = executor.execute(
            task_instance=mock_task,
            session=mock_session,
            execution_model=mock_execution,
            qid="Q0",
            username="test_user",
        )

        # Assert
        mock_task.preprocess.assert_called_once()
        mock_task.run.assert_called_once()
        assert result.output_parameters == {}

    def test_execute_saves_figures_when_present(self, executor):
        # Arrange
        mock_task = Mock()
        mock_task.get_name.return_value = "CheckFreq"
        mock_task.get_task_type.return_value = "qubit"
        mock_task.r2_threshold = 0.9

        mock_figure = Mock()
        postprocess_result = Mock(
            output_parameters={},
            figures=[mock_figure],
            raw_data=[],
        )
        mock_task.postprocess.return_value = postprocess_result
        mock_task.run.return_value = Mock(has_r2=lambda: False)

        # Act
        executor.execute(...)

        # Assert
        # FigurePersisterが呼ばれたことを確認
        ...
```

### 4.3 FlowSessionの統合テスト

```python
# tests/qdash/workflow/flow/test_session_integration.py

import pytest
from qdash.workflow.flow.session import FlowSession
from qdash.workflow.flow.session_config import FlowSessionConfig
from qdash.workflow.flow.session_factory import FlowSessionFactory
from qdash.workflow.engine.repositories.mongo import (
    MongoExecutionRepository,
    MongoTaskRepository,
)

class TestFlowSessionIntegration:
    """FlowSessionの統合テスト（インメモリ実装使用）"""

    def test_full_calibration_workflow(self):
        # Arrange
        config = FlowSessionConfig(
            username="test_user",
            chip_id="test_chip",
            qids=["Q0", "Q1"],
            execution_id="20240101-001",
            use_lock=False,  # テスト時はロック無効
        )

        execution_repo = MongoExecutionRepository(test_client)
        task_repo = MongoTaskRepository()

        session = FlowSessionFactory.create_for_test(
            config=config,
            execution_repository=execution_repo,
            task_repository=task_repo,
        )

        # Act
        session.start()

        # タスク実行をモック
        # ...

        session.finish()

        # Assert
        execution = execution_repo.find_by_id("20240101-001")
        assert execution is not None
        assert execution.status == ExecutionStatusModel.COMPLETED
```

---

## 5. 実装ロードマップ

### Phase 1: Repository層の導入（1-2週間）

**目標:** 既存コードへの影響を最小限に、テスタビリティの基盤を構築

**タスク:**

1. `src/qdash/workflow/engine/repositories/` ディレクトリ作成
2. `protocols.py` でインターフェース定義
3. `mongo.py` で既存DBモデルのラッパー実装
4. `memory.py` でテスト用インメモリ実装
5. `filesystem.py` でファイル保存の抽象化

**互換性:** 既存コードは変更なし、新規コードで段階的に使用

### Phase 2: TaskManagerの分割（2-3週間）

**目標:** 最大のSRP違反を解消

**タスク:**

1. `TaskStateManager` を抽出（純粋な状態管理）
2. `TaskResultProcessor` を抽出（保存処理）
3. `ValidationService` を抽出（検証ロジック）
4. `TaskHistoryRecorder` を実装し TaskResultHistory のイベント順を維持
5. `TaskExecutor` / `TaskExecutionResult` を作成し、R²検証後に永続化するフローを構築
6. 既存 `TaskManager` を段階的に新クラスに委譲

**互換性:** `TaskManager` の公開インターフェースは維持、内部実装を委譲

#### Phase 2 実行ステップ（Claude依頼用詳細）

1. **Step 0: 既存挙動の把握と安全網整備**
   - `src/qdash/workflow/engine/calibration/task_manager.py` の `execute_task` / `_save_all_results` / `_save_qubex_specific` の主要責務を洗い出し。
   - `tests/qdash/workflow/engine/calibration/` にスモークテストを追加して R²検証や図面保存など重要パスを固定。Mongo 依存テストは router/chip のテストと同様に Docker 内の Mongo コンテナへ `qubex_test` DB を追加し、そこで実行する。

2. **Step 1: Repository層の土台実装**
   - `src/qdash/workflow/engine/repositories/` を作成し、`protocols.py` で Task/Execution/Figure/CalibData インターフェースを定義。
   - Mongo ラッパーのみを整備し、`qubex_test` DB を利用した実 Mongo テストを追加。`TaskManager` 本体はまだ変更せず、インターフェース単体のテストを作成。

3. **Step 2: TaskStateManager 抽出**
   - 状態遷移ロジックと `CalibDataModel` 更新を `TaskStateManager` に切り出し、`TaskManager` は内部で委譲。
   - `tests/.../test_task_state_manager.py` で start/complete/fail/パラメータ設定/クリアのユニットテストを追加。

4. **Step 3: TaskHistoryRecorder & TaskResultProcessor 導入**
   - `TaskResultHistoryDocument.upsert_document` 呼び出しとファイル/DB保存処理をそれぞれ新クラス経由に変更。
   - モックリポジトリを使って保存順序/R²失敗時に永続化されないことを検証するテストを追加。

5. **Step 4: TaskExecutor 抽出**
   - `TaskManager.execute_task` のフローを `TaskExecutor` に移行し、当面は `TaskManager` がラッパーとして `TaskExecutor` を呼ぶ構成で Prefect 互換性を維持。
   - `tests/.../test_task_executor.py` にプリプロセス->実行->ポストプロセス->R²検証のモックテストを追加。

6. **Step 5: TaskManager 薄体化**
   - Prefect タスク (`execute_dynamic_task_by_qid` など) を `TaskExecutor`/`TaskExecutionResult` 対応に更新。
   - `BackendParamsUpdater` へ backend 固有処理を移し、FlowSession との連携を最終化。不要メソッドを削除し、統合テストを実行。

> 各ステップで新規クラスに対応するテストを追加し、既存挙動との乖離を防ぐこと。Claudeに依頼する際は、上記ステップ番号と対象ファイル/テストの組み合わせを明示する。

### Phase 3: ExecutionManagerの改善（1-2週間）

**目標:** DB直接アクセスの除去

**タスク:**

1. `ExecutionStateManager` を抽出（純粋な状態管理）
2. `ExecutionService` を作成（永続化を含む操作）
3. `_with_db_transaction` を `ExecutionRepository` に移動

**互換性:** 既存 `ExecutionManager` の公開インターフェースは維持

### Phase 4: FlowSessionの簡素化（1-2週間）

**目標:** ファサードパターン適用、依存性注入

**タスク:**

1. `FlowSessionConfig` 値オブジェクト作成
2. `FlowSessionFactory` でDI構成
3. `SessionStateStore` を導入し、Prefect戻り値とUI向けデータを集約
4. `FlowSession` を薄いファサードに変更し state_store と ExecutionService を橋渡し
5. グローバル変数 `_current_session` の扱いを検討

**互換性:** `init_calibration()`, `get_session()`, `finish_calibration()` のAPIは維持

---

## 6. リスクと対策

| リスク                       | 対策                                                           |
| ---------------------------- | -------------------------------------------------------------- |
| リファクタリング中の機能破壊 | Phase毎にテスト追加、既存APIは維持                             |
| 並行開発との競合             | feature branchで開発、小さなPRに分割                           |
| パフォーマンス低下           | レイヤー追加によるオーバーヘッドは軽微、プロファイリングで確認 |
| 学習コスト                   | ドキュメント整備、コードレビューでチーム共有                   |

---

## 7. 期待される効果

### テスタビリティ

| 指標                   | Before       | After            |
| ---------------------- | ------------ | ---------------- |
| 単体テスト可能なクラス | 0%           | 80%+             |
| モック不要のテスト     | 0%           | 60%+             |
| テスト実行速度         | DB依存で低速 | インメモリで高速 |

### 保守性

| 指標            | Before | After  |
| --------------- | ------ | ------ |
| クラス平均行数  | 500行  | 100行  |
| 責任の数/クラス | 5-8個  | 1-2個  |
| 変更影響範囲    | 広範囲 | 局所化 |

### 拡張性

- 新しいバックエンド追加: `BackendAdapter` 実装のみ
- 新しい永続化先追加: `Repository` 実装のみ
- 新しい検証ロジック追加: `ValidationService` 拡張のみ

---

## 8. 参考資料

- [Clean Architecture (Robert C. Martin)](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Dependency Injection in Python](https://python-dependency-injector.ets-labs.org/)
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)
- [SOLID Principles](https://en.wikipedia.org/wiki/SOLID)
