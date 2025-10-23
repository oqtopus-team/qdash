# リファクタリング計画（最終版）

## 現在の問題点

### 1. 保存処理の分散

- `task_manager.save()` が多数の箇所で呼ばれている
- 図表・生データ保存が TaskManager に分散
- タスク結果の保存が execute*dynamic_task*\* に分散

### 2. 役割分担の曖昧さ

- TaskManager: タスク状態管理 + 図表保存 + JSON 保存
- ExecutionManager: 実行全体管理 + データベース更新
- execute*dynamic_task*\*: 複雑な保存処理ロジック

### 3. データの一貫性

- 保存処理が複数箇所に分散
- エラー時の状態管理が複雑

## 提案する改善案：TaskManager での保存処理統合

### 基本方針

**TaskManager の保存処理を統合し、タスク実行と保存を一元管理する。BaseTask は既存の run() メソッドを維持し、TaskManager が統合された保存処理を担当する**

### Phase 1: TaskManager の保存処理統合

#### 1.1 統合された TaskManager

```python
# src/qdash/workflow/core/calibration/task_manager.py (拡張)
from pathlib import Path
import plotly.graph_objs as go
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

class TaskManager:
    """統合された保存処理を持つ TaskManager"""

    # 既存の属性...

    def execute_task(
        self,
        task_instance,
        session,
        execution_manager,
        qid: str
    ) -> tuple[ExecutionManager, TaskManager]:
        """タスク実行と保存を統合した管理"""

        try:
            # 1. タスク開始
            self.start_task(task_instance.name, task_instance.task_type, qid)

            # 2. 前処理（既存の BaseTask.preprocess を使用）
            preprocess_result = task_instance.preprocess(session, qid)
            if preprocess_result:
                self.put_input_parameters(
                    task_instance.name, preprocess_result.input_parameters,
                    task_type=task_instance.task_type, qid=qid
                )

            # 3. 実行（既存の BaseTask.run を使用）
            run_result = task_instance.run(session, qid)

            # 4. 後処理（既存の BaseTask.postprocess を使用）
            postprocess_result = task_instance.postprocess(
                session, execution_manager.execution_id, run_result, qid
            )

            # 5. 統合された保存処理（TaskManager が責任を持つ）
            self._save_all_results(
                task_instance, execution_manager, postprocess_result, qid
            )

            # 6. タスク完了
            self.update_task_status_to_completed(
                task_instance.name, task_type=task_instance.task_type, qid=qid
            )

        except Exception as e:
            # エラー処理
            self._handle_task_error(task_instance, execution_manager, qid, str(e))
            raise

        finally:
            # 終了処理
            self.end_task(task_instance.name, task_instance.task_type, qid)

        return execution_manager, self

    def _save_all_results(
        self,
        task_instance,
        execution_manager,
        postprocess_result,
        qid: str
    ) -> None:
        """統合された保存処理（TaskManager が責任を持つ）"""

        # 1. 出力パラメータ保存
        if postprocess_result.output_parameters:
            self.put_output_parameters(
                task_instance.name, postprocess_result.output_parameters,
                task_type=task_instance.task_type, qid=qid
            )

        # 2. 図表保存（既存メソッドを活用）
        if postprocess_result.figures:
            self.save_figures(
                postprocess_result.figures, task_instance.name,
                task_type=task_instance.task_type, qid=qid
            )

        # 3. 生データ保存（既存メソッドを活用）
        if postprocess_result.raw_data:
            self.save_raw_data(
                postprocess_result.raw_data, task_instance.name,
                task_type=task_instance.task_type, qid=qid
            )

        # 4. データベース保存
        task_result = self.get_task(
            task_instance.name, task_type=task_instance.task_type, qid=qid
        )
        TaskResultHistoryDocument.upsert_document(
            task_result, execution_manager.to_datamodel()
        )

        # 5. ExecutionManager 更新
        execution_manager.update_with_task_manager(self)

        # 6. バックエンド特有の保存処理
        self._save_backend_specific(task_instance, execution_manager, qid)

    def _save_backend_specific(self, task_instance, execution_manager, qid: str) -> None:
        """バックエンド特有の保存処理"""
        if task_instance.backend == "qubex":
            self._save_qubex_specific(task_instance, execution_manager, qid)
        elif task_instance.backend == "fake":
            self._save_fake_specific(task_instance, execution_manager, qid)

    def _save_qubex_specific(self, task_instance, execution_manager, qid: str) -> None:
        """Qubex特有の保存処理"""
        # 1. キャリブレーションノート保存
        # 2. パラメータ更新
        from qdash.dbmodel.qubit import QubitDocument
        from qdash.dbmodel.coupling import CouplingDocument

        output_parameters = self.get_output_parameter_by_task_name(
            task_instance.name, task_type=task_instance.task_type, qid=qid
        )

        if output_parameters:
            if task_instance.is_qubit_task():
                QubitDocument.update_calib_data(
                    username=execution_manager.username,
                    qid=qid,
                    chip_id=execution_manager.chip_id,
                    output_parameters=output_parameters,
                )
            elif task_instance.is_coupling_task():
                CouplingDocument.update_calib_data(
                    username=execution_manager.username,
                    qid=qid,
                    chip_id=execution_manager.chip_id,
                    output_parameters=output_parameters,
                )

    def _save_fake_specific(self, task_instance, execution_manager, qid: str) -> None:
        """Fake特有の保存処理"""
        # シミュレーションメタデータ保存など
        pass

    def _handle_task_error(self, task_instance, execution_manager, qid: str, error_msg: str) -> None:
        """エラー処理"""
        self.update_task_status_to_failed(
            task_instance.name, message=error_msg,
            task_type=task_instance.task_type, qid=qid
        )

        # エラー状態もデータベースに保存
        task_result = self.get_task(
            task_instance.name, task_type=task_instance.task_type, qid=qid
        )
        TaskResultHistoryDocument.upsert_document(
            task_result, execution_manager.to_datamodel()
        )
```

### Phase 2: 実行フローの簡素化

#### 2.1 簡素化された execute_dynamic_task

```python
# src/qdash/workflow/core/calibration/task.py (簡素化)
@task(name="execute-dynamic-task")
def execute_dynamic_task_by_qid(
    session: BaseSession,
    execution_manager: ExecutionManager,
    task_manager: TaskManager,
    task_instance: BaseTask,
    qid: str,
) -> tuple[ExecutionManager, TaskManager]:
    """簡素化されたタスク実行（保存処理は TaskManager が担当）"""

    # TaskManager が統合された実行・保存処理を担当
    return task_manager.execute_task(
        task_instance, session, execution_manager, qid
    )

@task(name="execute-dynamic-task-batch")
def execute_dynamic_task_batch(
    session: BaseSession,
    execution_manager: ExecutionManager,
    task_manager: TaskManager,
    task_instance: BaseTask,
    qids: list[str],
) -> tuple[ExecutionManager, TaskManager]:
    """バッチ実行も簡素化"""

    for qid in qids:
        execution_manager, task_manager = task_manager.execute_task(
            task_instance, session, execution_manager, qid
        )

    return execution_manager, task_manager
```

### Phase 3: Python Flow Editor での活用

#### 3.1 統合された保存処理を活用したヘルパー関数

```python
# src/qdash/workflow/helpers/flow_helpers.py
class FlowSession:
    """統合された保存処理を活用する FlowSession"""

    def execute_task(self, task_name: str, qid: str, task_details: dict = None) -> dict:
        """統合された保存処理を活用したシンプルなタスク実行"""

        # TaskManager作成
        task_manager = TaskManager(
            username=self.username,
            execution_id=self.execution_id,
            qids=[qid],
            calib_dir=self.execution_manager.calib_data_path
        )

        # タスクインスタンス取得
        task_instances = generate_task_instances(
            task_names=[task_name],
            task_details=task_details or {},
            backend=self.backend
        )

        task_instance = task_instances[task_name]

        # TaskManager の統合実行（保存処理は自動）
        self.execution_manager, task_manager = task_manager.execute_task(
            task_instance, self.session, self.execution_manager, qid
        )

        # 結果返却
        return task_manager.get_output_parameter_by_task_name(
            task_name, task_type=task_instance.get_task_type(), qid=qid
        )

    def execute_task_batch(self, task_name: str, qids: list[str], task_details: dict = None) -> dict:
        """バッチ実行も統合された保存処理を活用"""
        task_manager = TaskManager(
            username=self.username,
            execution_id=self.execution_id,
            qids=qids,
            calib_dir=self.execution_manager.calib_data_path
        )

        task_instances = generate_task_instances(
            task_names=[task_name],
            task_details=task_details or {},
            backend=self.backend
        )

        task_instance = task_instances[task_name]

        # バッチ実行
        for qid in qids:
            self.execution_manager, task_manager = task_manager.execute_task(
                task_instance, self.session, self.execution_manager, qid
            )

        # 全qidの結果を返す
        results = {}
        for qid in qids:
            results[qid] = task_manager.get_output_parameter_by_task_name(
                task_name, task_type=task_instance.get_task_type(), qid=qid
            )
        return results
```

## 実装順序

### Step 1: TaskManager の拡張

- `execute_task` メソッドの実装
- `_save_all_results` メソッドの実装
- バックエンド特有の保存処理の統合

### Step 2: 実行フローの簡素化

- `execute_dynamic_task_*` の簡素化
- 重複する保存処理の削除

### Step 3: 既存機能の動作確認

- 既存タスクの動作テスト
- Menu Editor からの実行テスト

### Step 4: Python Flow Editor 対応

- 統合された保存処理を活用
- シンプルなヘルパー関数の実装

## メリット

1. **既存設計との整合性**: BaseTask の run() メソッドを維持
2. **責任の明確化**: TaskManager がタスク管理と保存を一元化
3. **コードの簡素化**: 重複する保存処理の削除
4. **保守性の向上**: 保存ロジックが TaskManager に集約
5. **拡張性**: バックエンド特有の処理も統合

この方向性により、既存の設計を尊重しながら、より保守性の高い実装を実現できます。
