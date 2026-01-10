import os
import secrets
import urllib.parse
import hashlib
import base64
from typing import Optional

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    g,
    make_response,
    redirect,
    render_template_string,
    request,
)
from dash import Dash, html

# ローカル起動時に .env を読み込む（Render等の環境変数は上書きしない）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DOTENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(dotenv_path=DOTENV_PATH, override=False)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me")

# 環境変数
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY", "")
APP_BASE_URL = (os.environ.get("APP_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")

COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "Lax")
COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN") or None

AUTH_COOKIE = "sb-access-token"
REFRESH_COOKIE = "sb-refresh-token"
STATE_COOKIE = "sb-oauth-state"
CODE_VERIFIER_COOKIE = "sb-pkce-verifier"
APP_STATE_COOKIE = "app-oauth-state"


def _auth_debug_enabled() -> bool:
    return os.environ.get("AUTH_DEBUG", "").strip().lower() in {"1", "true", "yes"}


def _cookie_kwargs(http_only: bool = True, max_age: Optional[int] = None) -> dict:
    return {
        "httponly": http_only,
        "secure": COOKIE_SECURE,
        "samesite": COOKIE_SAMESITE,
        "domain": COOKIE_DOMAIN,
        "path": "/",
        **({"max_age": max_age} if max_age is not None else {}),
    }


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _safe_redirect_target(base_url: str, target: Optional[str]) -> str:
    """外部リダイレクトを防ぎつつ、指定がなければ / に戻す。"""
    if not target:
        return "/"

    parsed = urllib.parse.urlparse(target)
    # 絶対URLの場合は同一ホストのみ許可
    if parsed.scheme or parsed.netloc:
        base_host = urllib.parse.urlparse(base_url).netloc
        if parsed.netloc == base_host:
            path = parsed.path or "/"
            query = f"?{parsed.query}" if parsed.query else ""
            fragment = f"#{parsed.fragment}" if parsed.fragment else ""
            return f"{path}{query}{fragment}"
        return "/"

    # 相対パスの場合
    if not target.startswith("/"):
        return f"/{target}"
    return target


def _build_authorize_url(base_url: str, code_challenge: str, app_state: str) -> str:
    # Supabaseの state は Supabase 側に任せる（独自stateを渡すと bad_oauth_state の原因になり得る）
    # CSRF対策はアプリ独自の app_state を redirect_to に埋め込んで検証する
    redirect_uri = (
        f"{base_url}/auth/callback?{urllib.parse.urlencode({'app_state': app_state})}"
    )
    params = {
        "provider": "google",
        "redirect_to": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{SUPABASE_URL}/auth/v1/authorize?{urllib.parse.urlencode(params)}"


def _supabase_auth_post(path: str, payload: dict) -> requests.Response:
    """Supabase Auth REST API 呼び出し（POST）。"""
    url = f"{SUPABASE_URL}{path}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    return resp


def _set_session_cookies(
    resp, access_token: str, refresh_token: Optional[str], expires_in: Optional[int]
) -> None:
    resp.set_cookie(
        AUTH_COOKIE, access_token, **_cookie_kwargs(http_only=True, max_age=expires_in)
    )
    if refresh_token:
        resp.set_cookie(REFRESH_COOKIE, refresh_token, **_cookie_kwargs(http_only=True))


def _clear_session_cookies(resp) -> None:
    resp.set_cookie(AUTH_COOKIE, "", **_cookie_kwargs(http_only=True, max_age=0))
    resp.set_cookie(REFRESH_COOKIE, "", **_cookie_kwargs(http_only=True, max_age=0))


def _verify_token(access_token: str):
    """Supabase Auth で検証し、ユーザー情報を返す。失敗時は None."""
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {access_token}",
        }
        resp = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=10)
        if resp.status_code >= 400:
            if _auth_debug_enabled():
                body = resp.text
                trimmed = body[:200] + ("..." if len(body) > 200 else "")
                print(
                    f"[AUTH_DEBUG] verify_token failed status={resp.status_code} body={trimmed}"
                )
            return None
        return resp.json()  # /auth/v1/user はトップレベルが user オブジェクト
    except Exception as exc:
        if _auth_debug_enabled():
            print(f"[AUTH_DEBUG] verify_token exception: {exc}")
        return None


def _is_public_path(path: str) -> bool:
    return path.startswith(
        (
            "/auth/login",
            "/auth/callback",
            "/logout",
            "/login",
            "/assets/",
            "/static/",
            "/_dash-component-suites/",
            "/_dash-layout",
            "/_dash-dependencies",
            "/_favicon.ico",
        )
    ) or path in {"/login", "/auth/login", "/auth/callback"}


@app.before_request
def _require_auth():
    # Debug出力（シークレットは出さない）
    if _auth_debug_enabled() and request.path in {
        "/",
        "/auth/callback",
        "/logout",
        "/auth/login",
    }:
        print("---- AUTH_DEBUG ----")
        print(f"path={request.path}")
        print(f"method={request.method}")
        print(f"url={request.url}")
        if request.args:
            print(f"query={dict(request.args)}")
        print(f"host={request.host}")
        print(f"scheme={request.scheme}")
        ua = request.headers.get("User-Agent")
        if ua:
            print(f"user_agent={ua}")
        ref = request.headers.get("Referer")
        if ref:
            print(f"referer={ref}")
        print("--------------------")

    if _is_public_path(request.path):
        return None

    access_token = request.cookies.get(AUTH_COOKIE)
    if not access_token:
        return redirect("/login")

    user = _verify_token(access_token)
    if not user:
        resp = make_response(redirect("/login"))
        _clear_session_cookies(resp)
        return resp

    g.user = user
    return None


@app.route("/login")
def login_page():
    # シンプルなログインページ
    return render_template_string(
        """
        <!doctype html>
        <html lang="ja">
          <head><meta charset="utf-8"><title>Login</title></head>
          <body style="font-family:sans-serif; max-width:520px; margin:40px auto;">
            <h2>ログイン</h2>
            <p>Googleでログインしてください。</p>
            <div style="margin:16px 0;">
              <a href="/auth/login"
                 style="padding:10px 16px; background:#0070f3; color:#fff; text-decoration:none; border-radius:4px; display:inline-block;">
                 Googleでログイン
              </a>
            </div>
          </body>
        </html>
        """
    )


@app.route("/auth/login")
def auth_login():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return "SUPABASE_URL / SUPABASE_KEY (ANON) が未設定です", 500
    try:
        base_url = APP_BASE_URL
    except Exception as exc:
        return f"APP_BASE_URL invalid: {exc}", 400

    app_state = secrets.token_urlsafe(32)
    verifier = _pkce_verifier()
    challenge = _pkce_challenge(verifier)
    redirect_to_param = request.args.get("redirect_to", "/")
    redirect_to = _safe_redirect_target(base_url, redirect_to_param)

    url = _build_authorize_url(base_url, challenge, app_state)

    resp = make_response(redirect(url))
    # app_state / redirect は JS から見えても機密でないため HttpOnly=False
    resp.set_cookie(
        APP_STATE_COOKIE, app_state, **_cookie_kwargs(http_only=False, max_age=600)
    )
    resp.set_cookie(
        "redirect_to", redirect_to, **_cookie_kwargs(http_only=False, max_age=600)
    )
    # code_verifier は秘密なので HttpOnly
    resp.set_cookie(
        CODE_VERIFIER_COOKIE, verifier, **_cookie_kwargs(http_only=True, max_age=600)
    )
    return resp


@app.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")
    verifier = request.cookies.get(CODE_VERIFIER_COOKIE)
    app_state_param = request.args.get("app_state")
    app_state_cookie = request.cookies.get(APP_STATE_COOKIE)
    redirect_to_cookie = request.cookies.get("redirect_to")

    if not code:
        return (
            "No authorization code returned. ブラウザのCookieや設定を確認してください。",
            400,
        )
    if not verifier:
        return "Missing PKCE verifier cookie.", 400
    if not app_state_param or not app_state_cookie:
        return "Missing app_state. Please retry login.", 400
    if app_state_param != app_state_cookie:
        return "app_state mismatch. Please retry login.", 400

    # code を token に交換
    token_url = f"{SUPABASE_URL}/auth/v1/token?grant_type=pkce"
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }
    payload = {"auth_code": code, "code_verifier": verifier}

    try:
        resp_token = requests.post(token_url, json=payload, headers=headers, timeout=10)
    except Exception as exc:
        return f"Failed to exchange code: {exc}", 400

    if resp_token.status_code >= 400:
        return f"Token exchange failed: {resp_token.status_code} {resp_token.text}", 400

    session = resp_token.json()
    access_token = session.get("access_token")
    refresh_token = session.get("refresh_token")
    expires_in = session.get("expires_in")
    if not access_token:
        return f"No access_token in session response: {session}", 400

    redirect_to = _safe_redirect_target(APP_BASE_URL, redirect_to_cookie)

    resp = make_response(redirect(redirect_to))
    _set_session_cookies(resp, access_token, refresh_token, expires_in)
    # app_state / verifier を破棄
    resp.set_cookie(APP_STATE_COOKIE, "", **_cookie_kwargs(http_only=False, max_age=0))
    resp.set_cookie(
        CODE_VERIFIER_COOKIE, "", **_cookie_kwargs(http_only=True, max_age=0)
    )
    resp.set_cookie("redirect_to", "", **_cookie_kwargs(http_only=False, max_age=0))
    return resp


@app.route("/logout")
def logout():
    resp = make_response(redirect("/login"))
    _clear_session_cookies(resp)
    return resp


# --- Dash を Flask にマウント（最小ページ） ---
dash_app = Dash(
    __name__,
    server=app,  # type: ignore[arg-type]
    url_base_pathname="/",
    suppress_callback_exceptions=True,
)

dash_app.layout = html.Div(
    [
        html.H2("Dash (protected by Flask PKCE + HttpOnly Cookie)"),
        html.Div(id="user-info", children="ログイン中ユーザーを表示します"),
        html.A("ログアウト", href="/logout"),
    ]
)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
