# Copilot Task Analysis Feature - 設計仕様書

## 1. 概要

メトリクスモーダルにサイドパネル型のAIチャットを追加し、キャリブレーション結果の解釈・判断をLLMに相談できる機能を実装する。

### 背景

- メトリクスモーダルでは実験結果の画像（減衰カーブ、Rabiオシレーション等）やパラメータを閲覧できるが、結果の解釈には量子ビットキャリブレーションの専門知識が必要
- 現行のCopilotチャットはチップ全体の健全性分析に特化しており、個別タスクの詳細分析には対応していない
- 各タスクの`description`やパラメータ情報をLLMのコンテキストとして構造化し、専門的な分析支援を提供する

### ゴール

1. メトリクスモーダルからタスク結果（画像＋パラメータ＋実験コンテキスト）をLLMに送信し、解釈を相談できる
2. 各タスクに構造化された知識（`TaskKnowledge`）を定義し、LLMプロンプトの一部として活用する
3. LLMプロバイダを設定で切替可能にする（Ollama / OpenAI / Anthropic）

---

## 2. アーキテクチャ

### 2.1 全体構成

```
┌─────────────────────────────────────────┬──────────────────┐
│  Metrics Modal (既存3カラム)              │  AI Chat Panel   │
│  ┌─────┬──────┬────────────────┐        │                  │
│  │履歴  │タスク │詳細+画像        │        │  [コンテキスト]   │
│  │     │      │               │        │  CheckT1 / Q03   │
│  │     │      │  ┌──────────┐ │        │  T1=42.3μs       │
│  │     │      │  │ 減衰カーブ │ │  ──→  │                  │
│  │     │      │  └──────────┘ │        │  ユーザー質問      │
│  │     │      │               │        │                  │
│  │     │      │  Params Tables│        │  AI回答           │
│  └─────┴──────┴────────────────┘        │                  │
└─────────────────────────────────────────┴──────────────────┘
```

### 2.2 データフロー

```
ユーザーが「この結果について聞く」ボタンをクリック
    │
    ▼
コンテキスト構築 (フロントエンド)
    │  - TaskKnowledge (タスクの専門知識)
    │  - input_parameters / output_parameters / run_parameters
    │  - 量子ビット基本特性 (QubitModel.data)
    │  - メトリクス閾値 (metrics.yaml)
    │  - 結果画像 (figure_path → base64)
    │
    ▼
Next.js API Route (/api/chat/analysis)
    │
    ▼
Pydantic AI Agent (バックエンド)
    │  - deps: TaskAnalysisContext (構造化コンテキスト)
    │  - system_prompt: タスク知識 + ドメイン知識
    │  - user_message: ユーザーの質問
    │  - image: 結果画像 (マルチモーダル)
    │
    ▼
LLMプロバイダ (設定で切替)
    │  - OpenAI (gpt-4o) ← 推奨
    │  - Anthropic (claude-sonnet-4-5-20250929)
    │  - Ollama (ローカル)
    │
    ▼
構造化レスポンス → サイドパネルに表示
```

---

## 3. TaskKnowledge モデル

### 3.1 モデル定義

各キャリブレーションタスクにLLM向けの構造化知識を持たせる。

**ファイル**: `src/qdash/datamodel/task_knowledge.py`

```python
from pydantic import BaseModel, Field


class TaskKnowledge(BaseModel):
    """LLMに渡すタスクのドメイン知識を構造化するモデル。

    各キャリブレーションタスク（CheckT1, CheckRabi等）が
    ClassVarとしてこのモデルのインスタンスを持つ。
    サイドパネルチャットのシステムプロンプトに組み込まれ、
    LLMがキャリブレーション結果を正しく解釈するための
    コンテキストを提供する。
    """

    name: str = Field(
        description="タスク名（例: CheckT1）"
    )
    summary: str = Field(
        description="1行の実験サマリ（例: T1緩和時間の測定）"
    )
    what_it_measures: str = Field(
        description="何を測定するかの説明"
    )
    physical_principle: str = Field(
        description="物理的原理の簡潔な説明。"
        "パルスシーケンスや測定手法を含む"
    )
    expected_curve: str = Field(
        description="期待されるグラフの形状・特徴"
    )
    good_threshold: str = Field(
        description="良好/優秀と判断する定量的基準"
    )
    failure_modes: list[str] = Field(
        default_factory=list,
        description="よくある失敗パターンと原因の一覧"
    )
    tips: list[str] = Field(
        default_factory=list,
        description="結果を改善するための実践的なヒント"
    )

    def to_prompt(self) -> str:
        """システムプロンプト用のmarkdownテキストに変換する。"""
        lines = [
            f"## 実験: {self.name}",
            f"{self.summary}",
            "",
            f"### 測定対象",
            f"{self.what_it_measures}",
            "",
            f"### 物理的原理",
            f"{self.physical_principle}",
            "",
            f"### 期待されるグラフ",
            f"{self.expected_curve}",
            "",
            f"### 判断基準",
            f"{self.good_threshold}",
        ]
        if self.failure_modes:
            lines += [
                "",
                "### よくある失敗パターン",
                *[f"- {f}" for f in self.failure_modes],
            ]
        if self.tips:
            lines += [
                "",
                "### 改善のヒント",
                *[f"- {t}" for t in self.tips],
            ]
        return "\n".join(lines)
```

### 3.2 各タスクへの適用例

**ファイル**: 各 `src/qdash/workflow/calibtasks/qubex/*/` のタスククラス

```python
# src/qdash/workflow/calibtasks/qubex/one_qubit_coarse/check_t1.py

from typing import ClassVar
from qdash.datamodel.task_knowledge import TaskKnowledge

class CheckT1(QubexTask):
    name: str = "CheckT1"
    task_type: str = "qubit"

    knowledge: ClassVar[TaskKnowledge] = TaskKnowledge(
        name="CheckT1",
        summary="T1緩和時間の測定",
        what_it_measures="励起状態の寿命（エネルギー緩和時間 T1）",
        physical_principle=(
            "π/2パルスで量子ビットを|1⟩に励起した後、"
            "様々な待ち時間tの後に読み出しを行う。"
            "励起状態の占有率は exp(-t/T1) に従い減衰し、"
            "この指数減衰カーブをフィットしてT1を求める。"
        ),
        expected_curve=(
            "横軸: 待ち時間 (ns)、縦軸: 励起状態占有率 (0-1)。"
            "t=0 で1に近い値から始まり、指数関数的に減衰して"
            "長時間側でベースライン（~0）に収束する滑らかなカーブ。"
        ),
        good_threshold="T1 > 50μs で良好、T1 > 100μs で優秀",
        failure_modes=[
            "R²が低い（< 0.9）→ ノイズ過多、温度不安定、TLS欠陥との結合",
            "T1が以前より急激に短くなった → TLS（二準位系）欠陥との結合、パッケージング問題",
            "フィットカーブに振動が見える → 残留Rabiオシレーション、駆動周波数のずれ",
            "ベースラインが0にならない → 読み出しの校正不良、熱励起",
        ],
        tips=[
            "T1はTLS欠陥との結合で時間変動するため、複数回測定してトレンドを確認すると良い",
            "T1が短い場合、qubit frequencyをわずかに変えてTLS回避を試みることがある",
            "shots数を増やすとフィットの信頼性が向上する",
        ],
    )
    # ... (既存の input_parameters, run_parameters, output_parameters)
```

```python
# src/qdash/workflow/calibtasks/qubex/one_qubit_coarse/check_rabi.py

class CheckRabi(QubexTask):
    name: str = "CheckRabi"

    knowledge: ClassVar[TaskKnowledge] = TaskKnowledge(
        name="CheckRabi",
        summary="Rabiオシレーションの測定",
        what_it_measures=(
            "量子ビットの制御パルスに対する応答（Rabi振動）。"
            "πパルス振幅・周波数の決定に使用"
        ),
        physical_principle=(
            "共鳴周波数のマイクロ波パルスを様々な長さで印加し、"
            "|0⟩と|1⟩の間のコヒーレントな振動（Rabiオシレーション）を観測する。"
            "振動の周期からπパルスの長さと振幅を決定する。"
        ),
        expected_curve=(
            "横軸: パルス時間 (ns)、縦軸: 励起状態占有率 (0-1)。"
            "正弦波的な振動が見える。振動が減衰する場合はデコヒーレンスの影響。"
            "振幅が1に近いほど制御の質が高い。"
        ),
        good_threshold=(
            "Rabi振動のコントラスト > 0.8、"
            "R² > 0.9 でフィットが信頼できる"
        ),
        failure_modes=[
            "振動が見えない → 制御振幅が不適切（大きすぎる/小さすぎる）、周波数ずれ",
            "振動の減衰が速い → T2が短い、制御パルスの品質問題",
            "R²が低い → ノイズが大きい、shots数が不足",
            "rabi_distanceが小さい → |0⟩と|1⟩の分離が不十分、読み出し校正が必要",
        ],
        tips=[
            "control_amplitudeが範囲外の場合、デフォルト値(0.0125)にフォールバックされる",
            "maximum_rabi_frequencyからπパルスの最適振幅が計算される",
        ],
    )
```

```python
# src/qdash/workflow/calibtasks/qubex/one_qubit_coarse/check_ramsey.py

class CheckRamsey(QubexTask):
    name: str = "CheckRamsey"

    knowledge: ClassVar[TaskKnowledge] = TaskKnowledge(
        name="CheckRamsey",
        summary="Ramsey干渉実験によるqubit周波数精密測定とT2*測定",
        what_it_measures=(
            "量子ビットの正確な共鳴周波数（bare frequency）と "
            "自由誘導減衰時間 T2*"
        ),
        physical_principle=(
            "2つのπ/2パルスの間に可変の自由発展時間を挟むRamsey干渉実験。"
            "意図的なdetuning (Δf) を加えて振動パターンを作り、"
            "X軸・Y軸の両方で測定してIQプレーン上の軌跡を取得する。"
            "振動周波数からdetuningを補正してbare frequencyを決定し、"
            "振動の減衰からT2*を求める。"
        ),
        expected_curve=(
            "時間領域: 減衰する正弦波振動。"
            "XYプレーン: Bloch球赤道面上でのスパイラルパターン。"
            "X軸・Y軸それぞれに対して減衰振動カーブがフィットされる。"
        ),
        good_threshold="T2* > 20μs で良好、T2* > 40μs で優秀",
        failure_modes=[
            "X軸・Y軸の両方でR²が低い → 周波数が大きくずれている、デコヒーレンスが速い",
            "片方の軸のみフィット成功 → もう一方の軸は参考程度に扱う（正常動作）",
            "T2*がT1より大幅に短い → 純粋位相緩和が支配的、低周波ノイズ",
            "XYプレーンのスパイラルが歪んでいる → 制御パルスの忠実度問題",
        ],
        tips=[
            "X軸とY軸で独立にR²を評価し、高い方を採用する設計になっている",
            "detuning値を調整すると振動周期が変わり、フィット精度が改善する場合がある",
        ],
    )
```

### 3.3 TaskKnowledge の定義が必要なタスク一覧

以下の全タスクに `knowledge` ClassVar を追加する。

| カテゴリ | タスク名 | 優先度 |
|---------|---------|--------|
| **one_qubit_coarse** | CheckT1 | 高 |
| | CheckT2Echo | 高 |
| | CheckRabi | 高 |
| | CheckRamsey | 高 |
| | CheckQubitFrequency | 高 |
| | CheckReadoutFrequency | 中 |
| | CreatePIPulse | 中 |
| | CreateHPIPulse | 中 |
| | CheckPiPulse | 中 |
| | CheckHpiPulse | 中 |
| | CheckOptimalReadoutAmplitude | 中 |
| | CheckDispersiveShift | 中 |
| | ChevronPattern | 低 |
| **one_qubit_fine** | CheckDragHpiPulse | 中 |
| | CheckDragPiPulse | 中 |
| | CreateDragHpiPulse | 中 |
| | CreateDragPiPulse | 中 |
| **two_qubit** | CheckCrossResonance | 高 |
| | CheckZX90 | 高 |
| | CreateZX90 | 中 |
| | CheckBellState | 高 |
| | CheckBellStateTomography | 中 |
| **benchmark** | RandomizedBenchmarking | 中 |
| | X90InterleavedRB | 中 |
| | X180InterleavedRB | 中 |
| | ZX90InterleavedRB | 中 |
| **cw** | CheckResonatorSpectroscopy | 低 |
| | CheckResonatorFrequencies | 低 |
| | CheckQubitSpectroscopy | 低 |
| | CheckQubitFrequencies | 低 |
| | CheckReflectionCoefficient | 低 |
| | CheckElectricalDelay | 低 |
| | CheckReadoutAmplitude | 低 |
| **measurement** | ReadoutClassification | 中 |

---

## 4. TaskKnowledge の API 公開

タスクの `knowledge` をフロントエンドから取得できるようにする。

### 4.1 バックエンドエンドポイント

**ファイル**: `src/qdash/api/routers/task.py` に追加

```
GET /tasks/{task_name}/knowledge
```

**レスポンス**: `TaskKnowledge` モデルをそのまま返す

**実装方針**: `BaseTask.registry` からタスククラスを引き、`knowledge` ClassVar を返す。
`knowledge` が未定義のタスクには空の `TaskKnowledge` をフォールバックとして返す。

### 4.2 APIスキーマ

**ファイル**: `src/qdash/api/schemas/task.py` に追加

```python
class TaskKnowledgeResponse(BaseModel):
    name: str
    summary: str
    what_it_measures: str
    physical_principle: str
    expected_curve: str
    good_threshold: str
    failure_modes: list[str]
    tips: list[str]
    prompt_text: str  # to_prompt() の結果
```

---

## 5. Pydantic AI による分析エージェント

### 5.1 依存関係の追加

**ファイル**: `pyproject.toml`

```toml
[project.optional-dependencies]
copilot = [
    "pydantic-ai>=0.2",
]
```

### 5.2 分析コンテキストモデル

**ファイル**: `src/qdash/api/lib/copilot_analysis.py`

```python
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext


class TaskAnalysisContext(BaseModel):
    """タスク分析のためのLLMコンテキスト。

    サイドパネルチャットからLLMに渡される全てのコンテキスト情報を
    1つの型安全なモデルにまとめる。
    """

    # タスク知識
    task_knowledge_prompt: str = Field(
        description="TaskKnowledge.to_prompt()の結果"
    )

    # 量子ビット情報
    chip_id: str
    qid: str
    qubit_params: dict[str, Any] = Field(
        description="量子ビットの現在のパラメータ一覧"
        "（frequency, T1, T2, anharmonicity等）"
    )

    # 実験パラメータ
    input_parameters: dict[str, Any]
    output_parameters: dict[str, Any]
    run_parameters: dict[str, Any]

    # 結果の評価
    metric_value: float | None = None
    metric_unit: str = ""
    r2_value: float | None = None

    # 履歴コンテキスト
    recent_values: list[float] = Field(
        default_factory=list,
        description="直近の測定値リスト（トレンド判断用）"
    )


class AnalysisResponse(BaseModel):
    """LLMからの構造化された分析レスポンス。"""

    summary: str = Field(description="結果の1行サマリ")
    assessment: str = Field(description="good / warning / bad")
    explanation: str = Field(description="詳細な分析と解釈")
    potential_issues: list[str] = Field(
        default_factory=list,
        description="検出された潜在的な問題"
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="推奨される次のアクション"
    )
```

### 5.3 分析エージェント

**ファイル**: `src/qdash/api/lib/copilot_agent.py`

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.models.anthropic import AnthropicModel

from qdash.api.lib.copilot_analysis import TaskAnalysisContext, AnalysisResponse
from qdash.api.lib.copilot_config import CopilotConfig


def create_analysis_agent(config: CopilotConfig) -> Agent:
    """設定に基づいて分析エージェントを生成する。"""

    model = _resolve_model(config)

    agent = Agent(
        model,
        deps_type=TaskAnalysisContext,
        result_type=AnalysisResponse,  # 構造化出力（チャットモードでは不要にもできる）
        system_prompt=(
            "あなたは超伝導量子ビットのキャリブレーション専門家です。\n"
            "固定周波数トランズモン量子ビットの校正結果を分析し、\n"
            "実験者に分かりやすく解釈と推奨アクションを提供してください。\n"
        ),
    )

    @agent.system_prompt
    def add_task_context(ctx: RunContext[TaskAnalysisContext]) -> str:
        """タスク固有の知識をシステムプロンプトに注入する。"""
        return ctx.deps.task_knowledge_prompt

    @agent.system_prompt
    def add_qubit_context(ctx: RunContext[TaskAnalysisContext]) -> str:
        """量子ビットの基本特性をコンテキストに追加する。"""
        params = ctx.deps.qubit_params
        lines = [
            f"\n## 対象量子ビット: {ctx.deps.qid} (Chip: {ctx.deps.chip_id})",
            "\n### 現在のパラメータ",
        ]
        for key, val in params.items():
            if isinstance(val, dict) and "value" in val:
                lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
            else:
                lines.append(f"- {key}: {val}")
        return "\n".join(lines)

    @agent.system_prompt
    def add_experiment_context(ctx: RunContext[TaskAnalysisContext]) -> str:
        """実験の入出力パラメータをコンテキストに追加する。"""
        lines = ["\n## 今回の実験結果"]
        if ctx.deps.metric_value is not None:
            lines.append(
                f"**測定値**: {ctx.deps.metric_value} {ctx.deps.metric_unit}"
            )
        if ctx.deps.r2_value is not None:
            lines.append(f"**フィットR²**: {ctx.deps.r2_value}")
        if ctx.deps.recent_values:
            lines.append(
                f"**直近の値**: {ctx.deps.recent_values}"
            )
        return "\n".join(lines)

    return agent


def _resolve_model(config: CopilotConfig):
    """設定からLLMモデルインスタンスを生成する。"""
    provider = config.model.provider
    name = config.model.name

    if provider == "openai":
        return OpenAIModel(name)
    elif provider == "anthropic":
        return AnthropicModel(name)
    elif provider == "ollama":
        return OpenAIModel(
            name,
            base_url="http://localhost:11434/v1",
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")
```

---

## 6. バックエンド分析 API

### 6.1 エンドポイント

**ファイル**: `src/qdash/api/routers/copilot.py` に追加

```
POST /api/copilot/analyze
```

**リクエストボディ**:

```python
class AnalyzeRequest(BaseModel):
    task_name: str          # "CheckT1" 等
    chip_id: str
    qid: str
    execution_id: str
    task_id: str
    message: str            # ユーザーのメッセージ
    image_base64: str | None = None  # 結果画像（マルチモーダル用）
    conversation_history: list[dict] = []  # 会話履歴
```

**レスポンス**: ストリーミング or JSON

### 6.2 処理フロー

1. `task_name` から `BaseTask.registry` を参照し `TaskKnowledge` を取得
2. `execution_id` + `task_id` から `input/output/run_parameters` を取得
3. `chip_id` + `qid` から `QubitModel.data` （量子ビット基本特性）を取得
4. メトリクス履歴から直近の値を取得
5. `TaskAnalysisContext` を構築
6. Pydantic AI エージェントを実行
7. レスポンスを返す

---

## 7. フロントエンド実装

### 7.1 サイドパネルコンポーネント

**ファイル**: `ui/src/components/features/metrics/AnalysisChatPanel.tsx`（新規）

```
コンポーネント構成:

AnalysisChatPanel (サイドパネル本体)
├── ChatHeader (タスク名・量子ビットID表示)
├── ChatMessages (メッセージ一覧)
│   ├── SystemMessage (コンテキストサマリ表示)
│   ├── UserMessage
│   └── AssistantMessage
│       ├── assessment badge (good/warning/bad)
│       ├── explanation (markdown)
│       ├── issues list
│       └── recommendations list
└── ChatInput (テキスト入力 + 送信ボタン)
```

### 7.2 モーダルへの統合

**ファイル**: `ui/src/components/features/metrics/QubitMetricHistoryModal.tsx`（変更）

- タスク詳細パネルに「Ask AI」ボタンを追加
- ボタンクリックでサイドパネルを開く
- サイドパネルには選択中のタスク情報が自動的に渡される

**レイアウト変更**:

```
変更前: [履歴 25%] [タスク 25%] [詳細 50%]
変更後: [履歴 20%] [タスク 20%] [詳細 35%] [AIチャット 25%]
  （AIチャット非表示時は既存レイアウトを維持）
```

### 7.3 APIクライアント

`task generate` で自動生成されるが、手動で型を定義する場合：

**ファイル**: `ui/src/hooks/useAnalysisChat.ts`（新規）

- `POST /api/copilot/analyze` を呼ぶカスタムフック
- 会話履歴の管理
- 画像のbase64変換

---

## 8. 設定

### 8.1 copilot.yaml の拡張

**ファイル**: `config/copilot.yaml`

```yaml
model:
  provider: openai          # openai | anthropic | ollama
  name: gpt-4o
  temperature: 0.7
  max_tokens: 2048

analysis:
  enabled: true
  multimodal: true          # 画像をLLMに送るか
  language: ja              # 分析の言語
  max_conversation_turns: 10
```

### 8.2 環境変数

```env
# LLMプロバイダ認証
OPENAI_API_KEY=sk-...
# or
ANTHROPIC_API_KEY=sk-ant-...

# Copilot設定
NEXT_PUBLIC_COPILOT_ANALYSIS_ENABLED=true
```

---

## 9. 実装ステップ

### Phase 1: 基盤（バックエンド）

1. [ ] `TaskKnowledge` モデルを定義（`src/qdash/datamodel/task_knowledge.py`）
2. [ ] 主要タスク（CheckT1, CheckT2Echo, CheckRabi, CheckRamsey）に `knowledge` ClassVar を追加
3. [ ] `GET /tasks/{task_name}/knowledge` エンドポイントを追加
4. [ ] `pyproject.toml` に `pydantic-ai` を optional dependency として追加

### Phase 2: 分析エージェント（バックエンド）

5. [ ] `TaskAnalysisContext` / `AnalysisResponse` モデルを定義
6. [ ] `create_analysis_agent()` の実装（Pydantic AI）
7. [ ] `POST /api/copilot/analyze` エンドポイントの実装
8. [ ] マルチモーダル対応（画像をコンテキストに含める）
9. [ ] `copilot.yaml` の拡張（analysis セクション追加）

### Phase 3: フロントエンド

10. [ ] `AnalysisChatPanel` コンポーネントの実装
11. [ ] `QubitMetricHistoryModal` にサイドパネル統合
12. [ ] `CouplingMetricHistoryModal` にも同様の統合
13. [ ] `useAnalysisChat` フックの実装
14. [ ] 画像のbase64変換とAPI送信
15. [ ] `task generate` でAPIクライアント再生成

### Phase 4: 残りのタスク知識

16. [ ] 全タスクに `TaskKnowledge` を追加（上記タスク一覧を参照）
17. [ ] TaskKnowledge の内容レビュー（量子ビット専門家によるチェック）

### Phase 5: 拡張

18. [ ] ストリーミングレスポンス対応
19. [ ] 会話履歴の永続化（オプション）
20. [ ] 分析結果のエクスポート機能（オプション）

---

## 10. 関連ファイル一覧

### 新規作成

| ファイル | 内容 |
|---------|------|
| `src/qdash/datamodel/task_knowledge.py` | TaskKnowledge モデル |
| `src/qdash/api/lib/copilot_analysis.py` | 分析コンテキスト/レスポンスモデル |
| `src/qdash/api/lib/copilot_agent.py` | Pydantic AI エージェント |
| `ui/src/components/features/metrics/AnalysisChatPanel.tsx` | サイドパネルUI |
| `ui/src/hooks/useAnalysisChat.ts` | 分析チャットフック |

### 変更

| ファイル | 変更内容 |
|---------|---------|
| `src/qdash/workflow/calibtasks/qubex/**/*.py` | `knowledge` ClassVar 追加 (全タスク) |
| `src/qdash/api/routers/copilot.py` | `/analyze` エンドポイント追加 |
| `src/qdash/api/schemas/task.py` | `TaskKnowledgeResponse` 追加 |
| `ui/src/components/features/metrics/QubitMetricHistoryModal.tsx` | サイドパネル統合 |
| `ui/src/components/features/metrics/CouplingMetricHistoryModal.tsx` | サイドパネル統合 |
| `config/copilot.yaml` | `analysis` セクション追加 |
| `pyproject.toml` | `pydantic-ai` 依存追加 |

### 参考（読み取りのみ）

| ファイル | 参照内容 |
|---------|---------|
| `config/metrics.yaml` | メトリクス閾値・評価モード |
| `src/qdash/api/lib/copilot_config.py` | 既存のCopilot設定モデル |
| `ui/src/app/api/chat/route.ts` | 既存のチャットAPI（参考実装） |
| `ui/src/components/features/chat/` | 既存のチャットUI（参考実装） |

---

## 11. 技術的な注意事項

### マルチモーダル対応

- OpenAI GPT-4o / Anthropic Claude はネイティブで画像入力に対応
- Ollama はモデルによって非対応 → `multimodal: false` 設定で画像送信をスキップ
- 画像は `figure_path` から取得し、base64エンコードしてAPIに送信

### プロバイダ切替

- Pydantic AI がOpenAI / Anthropic / Ollama を統一的に扱える
- `copilot.yaml` の `model.provider` と `model.name` のみ変更すれば切替可能
- Ollama → OpenAI互換API (`base_url`) で対応

### 既存チャットとの共存

- 既存のCopilotチャット（チップ全体分析）はそのまま維持
- 新しい分析チャット（タスク個別分析）は独立したエンドポイント
- 将来的に統合する場合は、既存チャットもPydantic AIに移行するのが望ましい

### auto-generated コードへの影響

- `ui/src/client/` は `task generate` で再生成される
- バックエンドに新しいエンドポイントを追加した後、`task generate` を実行して型を再生成する
