# Python Flow Editor - Phase 2 Improvements (2025-01-24)

## 実装内容サマリー

### 1. FlowDocument削除の修正

**ファイル**: `/workspace/qdash/src/qdash/dbmodel/flow.py`

**問題**: `.find_one(...).delete()`がBunnetで正しく動作しない

**修正**:
```python
@classmethod
def delete_by_user_and_name(cls, username: str, name: str) -> bool:
    doc = cls.find_one({"username": username, "name": name}).run()
    if doc:
        doc.delete()
        return True
    return False
```

### 2. 保存時のコード検証機能

**ファイル**: `/workspace/qdash/src/qdash/api/routers/flow.py`

**機能**: AST（Abstract Syntax Tree）を使ってPythonコードを検証

**検証内容**:
- Pythonシンタックスエラーのチェック
- `@flow`デコレータの存在確認
- 指定されたentrypoint関数名の存在確認

**実装**:
```python
def validate_flow_code(code: str, expected_function_name: str) -> None:
    """Validate that Python code contains the expected @flow decorated function."""
    import ast
    
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Python syntax error: {e}")
    
    # Find all @flow decorated functions
    flow_functions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "flow":
                    flow_functions.append(node.name)
                elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == "flow":
                    flow_functions.append(node.name)
    
    if not flow_functions:
        raise HTTPException(status_code=400, detail="No @flow decorated function found")
    
    if expected_function_name not in flow_functions:
        raise HTTPException(
            status_code=400,
            detail=f"Flow function '{expected_function_name}' not found. Found: {', '.join(flow_functions)}"
        )
```

### 3. Flow名とEntrypoint Functionの分離

**背景**: 
- Flow名（ファイル名）とentrypoint関数名を一致させる必要があったが、不便だった
- ユーザーがどの関数をエントリーポイントにするか指定できるべき

**UIの変更**:
- "Entrypoint Function"フィールドを再追加
- Flow名とは独立して指定可能
- テンプレート読み込み時は自動設定

**ファイル**:
- `/workspace/qdash/ui/src/app/flow/new/page.tsx`
- `/workspace/qdash/ui/src/app/flow/[name]/page.tsx`

**フィールド**:
```tsx
<div className="form-control">
  <label className="label">
    <span className="label-text text-xs text-gray-400">
      Entrypoint Function
    </span>
  </label>
  <input
    type="text"
    placeholder="simple_flow"
    className="input input-bordered input-sm bg-[#3c3c3c] border-[#3e3e3e] text-white"
    value={flowFunctionName}
    onChange={(e) => setFlowFunctionName(e.target.value)}
  />
  <label className="label">
    <span className="label-text-alt text-xs text-gray-500">
      The @flow decorated function name in your code
    </span>
  </label>
</div>
```

### 4. Execution一覧でFlow名を表示

**問題**: Execution一覧で関数名（entrypoint）が表示されていたが、Flow名（ファイル名）の方が分かりやすい

**解決策**:

#### API側 (`flow.py`):
```python
# Execute時にflow_nameをparametersに自動注入
parameters: dict[str, Any] = {
    **flow.default_parameters,
    **request.parameters,
    "flow_name": name,  # Flow名を追加
}
```

#### flow_helpers.py:
```python
def init_calibration(
    username: str,
    chip_id: str,
    qids: list[str],
    execution_id: str | None = None,
    backend: str = "qubex",
    name: str | None = None,
    flow_name: str | None = None,  # 新規追加
    tags: list[str] | None = None,
    use_lock: bool = True,
    note: dict[str, Any] | None = None,
) -> FlowSession:
    # Priority: flow_name > name > auto-detect from Prefect
    display_name = flow_name or name
    if display_name is None:
        # Auto-detect from Prefect context
        ...
    
    _current_session = FlowSession(
        ...
        name=display_name,  # 表示名として使用
        ...
    )
```

#### 全テンプレートファイルの更新:
```python
@flow
def simple_flow(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    flow_name: str | None = None,  # 追加
):
    session = init_calibration(username, chip_id, qids, flow_name=flow_name)
    ...
```

**更新したテンプレート**: 7ファイル
- `simple_flow.py`
- `parallel_flow.py`
- `sequential_flow.py`
- `adaptive_flow.py`
- `schedule_flow.py`
- `custom_parallel_flow.py`
- `iterative_flow.py`

### 5. スキーマの変更

**ファイル**: `/workspace/qdash/src/qdash/api/schemas/flow.py`

```python
class SaveFlowRequest(BaseModel):
    name: str
    description: str = ""
    code: str
    flow_function_name: str | None = None  # オプショナル、未指定ならnameと同じ
    chip_id: str
    default_parameters: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
```

### 6. デプロイメントサービスの動作

**ファイル**: `/workspace/qdash/src/qdash/workflow/deployment_service.py`

- `flow_function_name`を使ってPythonファイルから関数をロード
- entrypointとして`{file_path}:{flow_function_name}`を使用
- 関数が存在しない場合は400エラー

## 使用例

### Flow作成:
1. Flow名: `my_calibration` → ファイル: `my_calibration.py`
2. Entrypoint Function: `simple_flow`
3. コード内: `@flow def simple_flow(...)`

### Execution一覧表示:
- 表示名: `my_calibration` (Flow名)
- 内部的なentrypoint: `simple_flow` (関数名)

## 利点

1. **柔軟性**: Flow名と関数名を独立して管理できる
2. **分かりやすさ**: Execution一覧でファイル名が表示される
3. **検証**: 保存時にコードとentrypoint関数の整合性を確認
4. **エラーハンドリング**: AST検証により明確なエラーメッセージ

## 関連ファイル

- `/workspace/qdash/src/qdash/dbmodel/flow.py`
- `/workspace/qdash/src/qdash/api/routers/flow.py`
- `/workspace/qdash/src/qdash/api/schemas/flow.py`
- `/workspace/qdash/src/qdash/workflow/helpers/flow_helpers.py`
- `/workspace/qdash/src/qdash/workflow/deployment_service.py`
- `/workspace/qdash/ui/src/app/flow/new/page.tsx`
- `/workspace/qdash/ui/src/app/flow/[name]/page.tsx`
- 全テンプレートファイル（7ファイル）
