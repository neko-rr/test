## 認証テスト用ミニコピー (testni)

- 目的: 既存コードに影響を与えず、`testni/` 内で Supabase 認証フローを単体確認する。
- 依存: 親ディレクトリの `components/` や `services/` などを再利用するため、`testni/server.py` と `testni/app.py` で親ディレクトリを `sys.path` に追加しています。

### 手順
1. `.env` を用意  
   - `testni/.env.example` をコピーして `testni/.env` を作成し、Supabase や APP_BASE_URL などを設定。
2. 起動  
   - `cd testni`  
   - `python server.py`
3. アクセス  
   - ブラウザで `APP_BASE_URL` に設定した URL（例: `http://127.0.0.1:8050`）へアクセス。

### 備考
- 既存プロジェクトは変更していません。`testni/` 配下のみ新規追加です。
- 認証フローの動作確認のみを想定しています。UI やデータは親ディレクトリの実装をそのまま利用します。

