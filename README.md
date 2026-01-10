# Google OAuth (Supabase) + Flask + Dash (Docker on Render)

サーバ側 PKCE コード交換＋ HttpOnly Cookie で Dash を入口保護する最小構成です。Docker で Render にデプロイできます。

## 前提条件

- Python 3.11 推奨（Docker は python:3.11-slim）
- Supabase アカウント（無料で作成可能）
- Render アカウント（無料で作成可能）
- Google Cloud Console アカウント（Google OAuth 設定用）

## セットアップ手順

### 1. Supabase の設定

1. [Supabase](https://supabase.com/)でアカウントを作成し、新しいプロジェクトを作成
2. プロジェクトの設定から以下を取得：
   - **Project URL** (`SUPABASE_URL`)
   - **anon/public key** (`SUPABASE_ANON_KEY`) ※互換で `SUPABASE_KEY` も可

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

### 3. ローカル環境でのテスト（PKCE ＋ HttpOnly Cookie）

1. リポジトリをクローン（またはこのプロジェクトを使用）
2. 仮想環境を作成してアクティベート：
   ```bash
   python -m venv venv  # 3.11 推奨（Dockerと合わせる）
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
   export SUPABASE_ANON_KEY="your-supabase-anon-key"  # または SUPABASE_KEY
   export SECRET_KEY="生成したランダム文字列"
   export APP_BASE_URL="http://127.0.0.1:8000"
   export COOKIE_SECURE="false"
   export COOKIE_SAMESITE="Lax"
   ```

   または `.env` ファイルを作成（本番環境では環境変数を推奨）

5. アプリケーションを起動：
   ```bash
   python app.py
   ```
6. ブラウザで `http://127.0.0.1:8000/login` にアクセスし、Google ログイン → `/` (Dash) 表示を確認
   - ログアウトは `/logout`（Google アカウントのサインアウトとは別）

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

#### 4.3 環境変数を設定（サーバ主体フロー）

Render ダッシュボードの **Environment** セクションで以下を追加（Git に入れない）：

- `SUPABASE_URL`: Supabase プロジェクトの URL
- `SUPABASE_ANON_KEY`: Supabase の anon/public key（互換: `SUPABASE_KEY`）
- `APP_BASE_URL`: Render 本番は `https://<your-render-app>.onrender.com`
- `SECRET_KEY`: ランダムな文字列（Flask セッション用。`python -c "import secrets; print(secrets.token_urlsafe(32))"` で生成）
- `COOKIE_SECURE`: 本番は `true` 推奨（HTTPS で Cookie を送るため）
- `COOKIE_SAMESITE`: `Lax` 推奨
- `PORT`: Render が自動設定（Dockerfile が `$PORT` を参照）

> Dockerfile の `ENV PORT=8000` はローカル実行時のデフォルトです。Render では `$PORT` が注入され、シェル経由で展開された値を使って gunicorn が起動します。

### 5. Supabase / Google の設定（サーバ主体フロー：PKCE 交換をサーバで実施）

- Supabase 側
  - Authentication → Providers → Google を ON
  - Authentication → URL Configuration → Redirect URLs に以下を追加（**ポート/ホスト完全一致**）
    - `http://127.0.0.1:8000/auth/callback`
    - `https://<your-render-app>.onrender.com/auth/callback`
- Google Cloud Console 側
  - Authorized redirect URIs に **Supabase 標準** を登録
    - `https://<project-ref>.supabase.co/auth/v1/callback`
  - Authorized JavaScript origins にローカル/本番の origin を登録（例: `http://127.0.0.1:8000`, `https://<your-render-app>.onrender.com`）

#### 4.4 デプロイ

1. **Create Web Service** をクリック
2. デプロイが完了するまで待機（数分かかります）
3. デプロイ完了後、提供された URL にアクセスして動作確認

## ファイル構成

```
.
├── app.py                 # メインアプリ（Flask + Dash, サーバ側PKCE）
├── supabase_client.py     # Supabaseクライアント設定（シンプル版）
├── flask_storage.py       # （未使用なら削除可）
├── requirements.txt       # 依存関係
├── Dockerfile             # Render 用（Dockerデプロイ）
├── .dockerignore
├── .gitignore
└── README.md
```

## トラブルシューティング

### 認証が失敗する場合

1. Supabase と Google Cloud Console の両方でリダイレクト URI が正しく設定されているか確認
2. 環境変数が正しく設定されているか確認
3. Render のログを確認（**Logs** タブ）

### セッションが保持されない場合

- `SECRET_KEY` が設定されているか確認
- Cookie の設定を確認（本番は HTTPS 必須、`COOKIE_SECURE=true` 推奨）

## 参考リンク

- [Supabase Auth Documentation](https://supabase.com/docs/guides/auth)
- [Supabase Error Codes](https://supabase.com/docs/guides/auth/debugging/error-codes)
- [Supabase Login with Google](https://supabase.com/docs/guides/auth/social-login/auth-google?queryGroups=framework&framework=express)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Render Documentation](https://render.com/docs)
