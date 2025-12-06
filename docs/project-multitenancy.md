# プロジェクト基盤のマルチテナンシー化 設計書

## 1. 依頼内容（要約）

- 既存実装では全てのキャリブレーションデータがユーザー単位で所有されているが、他ユーザーに参照のみで共有したい。
- そのため各ユーザーが「プロジェクト」を作成し、全データを `project_id` に紐づけ、他ユーザーを参照権限で招待する構成を検討したい。
- 代替案も考慮し現行実装を踏まえて最も適した方式を設計し、具体的仕様を提示してほしい。

## 2. 採用したアーキテクチャ設計

### 2.1 コンセプト

- すべてのデータを「プロジェクト」という共有単位にぶら下げる。
- `ProjectDocument` がワークスペース本体、`ProjectMembershipDocument` がユーザーとプロジェクトの関係を表現。
- ルートデータ（Chip/Qubit/Coupling/Execution…）は `project_id` を必須フィールドとして持ち、クエリやインデックスも `(project_id, …)` を先頭に構成する。

### 2.2 モデル仕様

- **ProjectModel / ProjectDocument**
  - `project_id`, `owner_username`, `name`, `description`, `tags`, `default_role`, `system_info`
  - インデックス: `project_id` 一意, `(owner_username, name)` ユニーク
- **ProjectMembershipModel / ProjectMembershipDocument**
  - `project_id`, `username`, `role` (`owner|editor|viewer`), `status` (`pending|active|revoked`), `invited_by`, `last_accessed_at`
  - インデックス: `(project_id, username)` ユニーク, `(username, status)` 参照
- **既存ドキュメントの変更**
  - Chip/Qubit/Coupling/Execution/Task/TaskResult/Backend/Tag/History/ExecutionLock/ExecutionCounter/Flow 等すべてに `project_id` フィールドを追加し、主要インデックスを `project_id` 先頭に再設計。
  - Datamodel 層にも `project_id` を追加し、UI/APIへ透過的に流す。

### 2.3 サービス責務

- `ProjectService`
  - `create_project`: プロジェクト作成 + owner メンバーシップ登録
  - `ensure_default_project`: ユーザーのデフォルトプロジェクト存在保証（初回登録時に使用）
  - `invite_viewer`: 閲覧招待などの補助メソッド

### 2.4 認証/権限フロー

- `/auth/register` でユーザー登録後に `ProjectService.ensure_default_project` を実行し、`UserDocument.default_project_id` をセット。
- `/auth/login` / `/auth/register` / `/auth/me` のレスポンスには `default_project_id` を含め、クライアントが即座にプロジェクト境界を把握できるようにする。
- 今後の API ではリクエストヘッダ/パスで `project_id` を受け取り、`ProjectMembershipDocument` によって `viewer/editor/owner` 権限を判定する。

### 2.5 インデックス/クエリ方針

- 代表例: `execution_history` に `project_id + chip_id + start_at`、`project_id + chip_id`、`project_id + username + start_at` の複合インデックスを付与し、マルチテナントでも効率的なメトリクス取得を保証。
- 他コレクションも同一方針で `project_id` をパーティションキー化する。

### 2.6 ER 図イメージ

```
User --< ProjectMembership >-- Project --< Chip/Qubit/Coupling/... >
```

その他のコレクション（Task, Backend, Tag, Flow, History 系）はすべて `project_id` を共有キーとして参照。

## 3. 実装状況

| ステータス | 内容                                                                                                   |
| ---------- | ------------------------------------------------------------------------------------------------------ |
| ✅ 完了    | `ProjectModel` / `ProjectMembershipModel` （`src/qdash/datamodel/project.py`）を定義。                 |
| ✅ 完了    | Bunnet ドキュメント `ProjectDocument` / `ProjectMembershipDocument` 作成、`document_models()` に登録。 |
| ✅ 完了    | `ProjectService` 実装（デフォルトプロジェクト作成ロジック含む）。                                      |
| ✅ 完了    | `UserDocument` に `default_project_id` 追加、認証フローでのデフォルトプロジェクト自動作成を実装。      |
| ✅ 完了    | Auth API レスポンス・OpenAPI・フロントエンド型定義に `default_project_id` を追加。                     |
| ✅ 完了    | Datamodel（Chip/Qubit/Coupling/Execution/Task/Backend etc.）へ `project_id` フィールドを追加。         |
| ✅ 完了    | Bunnet ドキュメント側での `project_id` 導入・インデックス付け。全14コレクション対応完了。              |
| ✅ 完了    | プロジェクト権限依存関係 (`src/qdash/api/lib/project.py`) - `ProjectContext`, 各権限レベルの依存関係。 |
| ✅ 完了    | プロジェクト管理 API (`src/qdash/api/routers/project.py`) - CRUD、メンバー招待/削除、オーナー移譲。    |
| ✅ 完了    | データ移行スクリプト (`src/qdash/dbmodel/migration.py`) - 既存データへの `project_id` 付与。           |
| ✅ 完了    | インデックスドキュメント更新 (`docs/database-indexes.md`) - 全コレクションのインデックス定義。         |
| ⏳ 未着手  | 既存 API エンドポイントへの `project_id` 統合（chip, execution, calibration 等）。                     |
| ⏳ 未着手  | フロントエンド UI でのプロジェクト切り替え・管理画面。                                                 |
| ⏳ 未着手  | 自動テストの拡充（ProjectService、認証レスポンス、API ガード等）。                                     |

## 3.1 新規作成ファイル一覧

| ファイル                           | 説明                                                                                                                |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `src/qdash/api/lib/project.py`     | プロジェクト権限チェック依存関係 (`get_project_context`, `get_project_context_editor`, `get_project_context_owner`) |
| `src/qdash/api/schemas/project.py` | プロジェクト API のリクエスト/レスポンススキーマ                                                                    |
| `src/qdash/api/routers/project.py` | プロジェクト管理 REST API                                                                                           |
| `src/qdash/dbmodel/migration.py`   | マルチテナンシー移行スクリプト                                                                                      |

## 3.2 プロジェクト API エンドポイント

| メソッド | パス                                        | 説明                       | 権限             |
| -------- | ------------------------------------------- | -------------------------- | ---------------- |
| POST     | `/projects`                                 | プロジェクト作成           | 認証済みユーザー |
| GET      | `/projects`                                 | ユーザーのプロジェクト一覧 | 認証済みユーザー |
| GET      | `/projects/{project_id}`                    | プロジェクト詳細取得       | viewer以上       |
| PATCH    | `/projects/{project_id}`                    | プロジェクト更新           | owner            |
| DELETE   | `/projects/{project_id}`                    | プロジェクト削除           | owner            |
| GET      | `/projects/{project_id}/members`            | メンバー一覧               | viewer以上       |
| POST     | `/projects/{project_id}/members`            | メンバー招待               | owner            |
| PATCH    | `/projects/{project_id}/members/{username}` | メンバー権限変更           | owner            |
| DELETE   | `/projects/{project_id}/members/{username}` | メンバー削除               | owner            |
| POST     | `/projects/{project_id}/transfer`           | オーナー移譲               | owner            |

## 3.3 移行手順

```bash
# 1. ドライラン（変更内容確認）
python -m qdash.dbmodel.migration

# 2. 実際の移行実行
python -m qdash.dbmodel.migration --execute
```

## 4. 今後の実装ガイドライン

1. **データ移行とインデックス再構築**  
   既存データに `project_id` を付与し、`username` ベースのインデックスを段階的に置き換える。
2. **API 層の `project_id` 必須化**  
   ヘッダ/パラメータでプロジェクトを指定→`ProjectMembershipDocument` で権限チェック→クエリを `project_id` フィルタに切り替える。
3. **プロジェクト管理 UI/API**  
   プロジェクト作成・メンバー招待・権限変更フローを整備し、`viewer` / `editor` / `owner` の操作境界を明確化。
4. **追加テスト**  
   サービス層・API 層・移行処理のテストを用意し、マルチテナント対応によるリグレッションを防止。
