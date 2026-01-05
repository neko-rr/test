import os
import sys

import dash
from dash import html
from flask import g, request

# 親ディレクトリを import パスに追加し、既存の components/services を再利用
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Load environment variables EARLY so services read correct .env (models, flags)
try:
    from dotenv import load_dotenv

    project_root = os.path.dirname(os.path.abspath(__file__))
    dotenv_path = os.path.join(project_root, ".env")
    load_dotenv(dotenv_path=dotenv_path, override=False)
    print("DEBUG: Early .env loaded before services imports")
except Exception as _early_env_err:
    print(f"DEBUG: Early .env load skipped: {_early_env_err}")


def create_app(server=None) -> dash.Dash:
    """
    認証確認用の最小Dashのみを提供する。
    認証フロー自体は server.py の before_request が担う。
    """
    app = dash.Dash(
        __name__,
        server=server,
        suppress_callback_exceptions=True,
        use_pages=False,
        meta_tags=[
            {
                "name": "viewport",
                "content": "width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no",
            }
        ],
    )
    app.title = "Auth minimal"

    def serve_layout():
        # before_request で g に詰められた情報を表示する
        user_id = getattr(g, "user_id", None)
        host = request.host
        path = request.path
        scheme = request.scheme
        return html.Div(
            style={"fontFamily": "sans-serif", "maxWidth": "640px", "margin": "40px auto"},
            children=[
                html.H2("ログイン確認"),
                html.P("Supabase Auth (Google) が通ればこのページが表示されます。"),
                html.Div(
                    style={"padding": "12px 16px", "background": "#f5f5f5", "borderRadius": "8px"},
                    children=[
                        html.Div(f"user_id: {user_id}"),
                        html.Div(f"scheme: {scheme}"),
                        html.Div(f"host: {host}"),
                        html.Div(f"path: {path}"),
                    ],
                ),
                html.Div(style={"marginTop": "16px"}, children=html.A("ログアウト", href="/auth/logout")),
            ],
        )

    app.layout = serve_layout
    return app


if __name__ == "__main__":
    import os

    app = create_app()
    server = app.server
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port)
