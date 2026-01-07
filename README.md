# Google OAuth with Flask and Supabase on Render

このプロジェクトは、Flask アプリケーションに Google OAuth 認証を実装し、Render にデプロイするためのサンプルです。

## 前提条件

- Python 3.8 以上
- Supabase アカウント（無料で作成可能）
- Render アカウント（無料で作成可能）
- Google Cloud Console アカウント（Google OAuth 設定用）

## セットアップ手順

### 1. Supabase の設定

1. [Supabase](https://supabase.com/)でアカウントを作成し、新しいプロジェクトを作成
2. プロジェクトの設定から以下を取得：
   - **Project URL** (`SUPABASE_URL`)
   - **anon/public key** (`SUPABASE_KEY`)

### 2. Supabase で Google OAuth を有効化

1. Supabase ダッシュボードで、**Authentication** → **Providers** に移動
2. **Google** プロバイダーを有効化
3. Google Cloud Console で以下を設定：
   - [Google Cloud Console](https://console.cloud.google.com/)にアクセス
   - 新しいプロジェクトを作成（または既存のプロジェクトを選択）
   - **API とサービス** → **認証情報** に移動
   - **OAuth 2.0 クライアント ID** を作成
   - **承認済みのリダイレクト URI** に以下を追加：
     ```
     https://[your-project-ref].supabase.co/auth/v1/callback
     ```
   - **クライアント ID** と **クライアント シークレット** をコピー
4. Supabase の Google プロバイダー設定に、コピーした**クライアント ID**と**クライアント シークレット**を入力して保存

### 3. ローカル環境でのテスト

1. リポジトリをクローン（またはこのプロジェクトを使用）
2. 仮想環境を作成してアクティベート：
   ```bash
   python -m venv venv  # 3.14は、依存ライブラリ側（httpcore）が対応していない。本番のDockerfile が python:3.11-slimらしい
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
   ```bash
   py -3.11 -m venv venv
   ```
3. 依存関係をインストール：
   ```bash
   pip install -r requirements.txt
   ```
4. 環境変数を設定：

   `SECRET_KEY`は、セッションの署名に使用される重要な値です。以下のコマンドでランダムな文字列を生成できます：

   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   環境変数を設定：

   ```bash
   export SUPABASE_URL="your-supabase-project-url"
   export SUPABASE_KEY="your-supabase-anon-key"
   export SECRET_KEY="生成したランダム文字列"
   ```

   または `.env` ファイルを作成（本番環境では使用しないでください）

5. アプリケーションを起動：
   ```bash
   python app.py
   ```
6. ブラウザで `http://localhost:8000` にアクセス

### 4. Render へのデプロイ（Docker）

#### 4.1 GitHub にプッシュ

1. このプロジェクトを GitHub リポジトリにプッシュ：
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/yourusername/your-repo.git
   git push -u origin main
   ```

#### 4.2 Render で Web サービスを作成（Docker）

1. [Render Dashboard](https://dashboard.render.com/)にログイン
2. **New +** → **Web Service** を選択
3. GitHub リポジトリを接続
4. **Runtime**: Docker を選択（ルートの `Dockerfile` を使用）
5. **Plan**: Free（または有料プラン）

#### 4.3 環境変数を設定

Render ダッシュボードの **Environment** セクションで以下を追加（Git に入れない）：

- `SUPABASE_URL`: Supabase プロジェクトの URL
- `SUPABASE_ANON_KEY`: Supabase の anon/public key（互換のため `SUPABASE_KEY` を残す場合は両方設定推奨）
- `SECRET_KEY`: ランダムな文字列（Flask セッション用。`python -c "import secrets; print(secrets.token_urlsafe(32))"` で生成）
- `PORT`: Render が自動設定（手動で設定する必要はありません）

> Dockerfile の `ENV PORT=8000` はローカル実行時のデフォルトです。Render では `$PORT` が注入され、シェル経由で展開された値を使って gunicorn が起動します。

### 5. supabase-js 初期化の注意

- ブラウザ側で supabase-js v2 を使う際は、`window.__supabaseClient = window.__supabaseClient || createClient(...)` のように一度だけ生成し、再利用してください（重複初期化による `Identifier 'supabase' has already been declared` を防ぐため）。
- CDN 読み込みは各ページ 1 回にすること。

### 5. Supabase / Google の設定（クライアント主体フロー）

- Supabase 側
  - Authentication → Providers → Google を ON
  - Authentication → URL Configuration → Redirect URLs に以下を追加
    - `http://127.0.0.1:8000/auth/callback`
    - `https://<your-render-app>.onrender.com/auth/callback`
- Google Cloud Console 側
  - Authorized redirect URIs に **Supabase 標準** を登録
    - `https://<project-ref>.supabase.co/auth/v1/callback`
  - （アプリの `/auth/callback` は Google 側に登録しない。Supabase→ アプリへの遷移先のため）

#### 4.4 リダイレクト URI を更新

Render にデプロイ後、以下の URL を取得：

```
https://your-app-name.onrender.com/callback
```

この URL を以下に追加する必要があります：

1. **Supabase 側**:

   - Supabase ダッシュボード → **Authentication** → **URL Configuration**
   - **Redirect URLs** に追加：
     ```
     https://your-app-name.onrender.com/callback
     ```

2. **Google Cloud Console 側**:
   - Google Cloud Console → **認証情報** → OAuth 2.0 クライアント ID
   - **承認済みのリダイレクト URI** に追加：
     ```
     https://your-app-name.onrender.com/callback
     ```

#### 4.5 デプロイ

1. **Create Web Service** をクリック
2. デプロイが完了するまで待機（数分かかります）
3. デプロイ完了後、提供された URL にアクセスして動作確認

## ファイル構成

```
.
├── app.py                 # メインアプリケーションファイル
├── flask_storage.py       # Flaskセッションストレージ
├── supabase_client.py     # Supabaseクライアント設定
├── requirements.txt       # Python依存関係
├── Procfile              # Render用起動コマンド
├── .gitignore           # Git除外ファイル
└── README.md            # このファイル
```

## トラブルシューティング

### 認証が失敗する場合

1. Supabase と Google Cloud Console の両方でリダイレクト URI が正しく設定されているか確認
2. 環境変数が正しく設定されているか確認
3. Render のログを確認（**Logs** タブ）

### セッションが保持されない場合

- `SECRET_KEY`が設定されているか確認
- Cookie の設定を確認（HTTPS が必要な場合があります）

## 参考リンク

- [Supabase Auth Documentation](https://supabase.com/docs/guides/auth)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Render Documentation](https://render.com/docs)
