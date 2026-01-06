# Google OAuth with Flask and Supabase on Render

このプロジェクトは、FlaskアプリケーションにGoogle OAuth認証を実装し、Renderにデプロイするためのサンプルです。

## 前提条件

- Python 3.8以上
- Supabaseアカウント（無料で作成可能）
- Renderアカウント（無料で作成可能）
- Google Cloud Consoleアカウント（Google OAuth設定用）

## セットアップ手順

### 1. Supabaseの設定

1. [Supabase](https://supabase.com/)でアカウントを作成し、新しいプロジェクトを作成
2. プロジェクトの設定から以下を取得：
   - **Project URL** (`SUPABASE_URL`)
   - **anon/public key** (`SUPABASE_KEY`)

### 2. SupabaseでGoogle OAuthを有効化

1. Supabaseダッシュボードで、**Authentication** → **Providers** に移動
2. **Google** プロバイダーを有効化
3. Google Cloud Consoleで以下を設定：
   - [Google Cloud Console](https://console.cloud.google.com/)にアクセス
   - 新しいプロジェクトを作成（または既存のプロジェクトを選択）
   - **APIとサービス** → **認証情報** に移動
   - **OAuth 2.0 クライアント ID** を作成
   - **承認済みのリダイレクト URI** に以下を追加：
     ```
     https://[your-project-ref].supabase.co/auth/v1/callback
     ```
   - **クライアント ID** と **クライアント シークレット** をコピー
4. SupabaseのGoogleプロバイダー設定に、コピーした**クライアント ID**と**クライアント シークレット**を入力して保存

### 3. ローカル環境でのテスト

1. リポジトリをクローン（またはこのプロジェクトを使用）
2. 仮想環境を作成してアクティベート：
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
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

### 4. Renderへのデプロイ

#### 4.1 GitHubにプッシュ

1. このプロジェクトをGitHubリポジトリにプッシュ：
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/yourusername/your-repo.git
   git push -u origin main
   ```

#### 4.2 RenderでWebサービスを作成

1. [Render Dashboard](https://dashboard.render.com/)にログイン
2. **New +** → **Web Service** を選択
3. GitHubリポジトリを接続
4. 以下の設定を行う：
   - **Name**: 任意の名前（例: `flask-google-oauth`）
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Plan**: Free（または有料プラン）

#### 4.3 環境変数を設定

Renderダッシュボードの **Environment** セクションで以下を追加：

- `SUPABASE_URL`: SupabaseプロジェクトのURL
- `SUPABASE_KEY`: Supabaseのanon/public key
- `SECRET_KEY`: ランダムな文字列（本番環境用の秘密鍵）
  - 生成方法: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
  - **重要**: 本番環境では必ず強力なランダム文字列を使用してください
- `PORT`: Renderが自動設定（手動で設定する必要はありません）

#### 4.4 リダイレクトURIを更新

Renderにデプロイ後、以下のURLを取得：
```
https://your-app-name.onrender.com/callback
```

このURLを以下に追加する必要があります：

1. **Supabase側**:
   - Supabaseダッシュボード → **Authentication** → **URL Configuration**
   - **Redirect URLs** に追加：
     ```
     https://your-app-name.onrender.com/callback
     ```

2. **Google Cloud Console側**:
   - Google Cloud Console → **認証情報** → OAuth 2.0 クライアント ID
   - **承認済みのリダイレクト URI** に追加：
     ```
     https://your-app-name.onrender.com/callback
     ```

#### 4.5 デプロイ

1. **Create Web Service** をクリック
2. デプロイが完了するまで待機（数分かかります）
3. デプロイ完了後、提供されたURLにアクセスして動作確認

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

1. SupabaseとGoogle Cloud Consoleの両方でリダイレクトURIが正しく設定されているか確認
2. 環境変数が正しく設定されているか確認
3. Renderのログを確認（**Logs** タブ）

### セッションが保持されない場合

- `SECRET_KEY`が設定されているか確認
- Cookieの設定を確認（HTTPSが必要な場合があります）

## 参考リンク

- [Supabase Auth Documentation](https://supabase.com/docs/guides/auth)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Render Documentation](https://render.com/docs)

