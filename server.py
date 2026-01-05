# -*- coding: utf-8 -*-
"""
Flask エントリポイント。Supabase Auth (Google OAuth) を用い、
JWT を HttpOnly Cookie で保持し、入口で検証して Dash を保護する。
"""

import base64
import hashlib
import os
import secrets
import sys
import urllib.parse
from urllib.parse import urlparse
from typing import Optional

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    g,
    jsonify,
    make_response,
    redirect,
    render_template_string,
    request,
)

# 親ディレクトリを import パスに追加し、既存の app/components/services を再利用
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from services.supabase_client import get_user_client

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DOTENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(dotenv_path=DOTENV_PATH, override=False)

SUPABASE_URL = os.getenv("PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL") or ""
PUBLISHABLE_KEY = (
    os.getenv("PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY")
    or os.getenv("SUPABASE_KEY")
    or ""
)
APP_BASE_URL = (os.getenv("APP_BASE_URL") or "").rstrip("/")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "Lax")
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None

AUTH_COOKIE = "sb-access-token"
REFRESH_COOKIE = "sb-refresh-token"
STATE_COOKIE = "sb-oauth-state"
CODE_VERIFIER_COOKIE = "sb-pkce-verifier"
REDIRECT_COOKIE = "sb-redirect-to"


def _cookie_kwargs(http_only: bool = True, max_age: Optional[int] = None) -> dict:
    return {
        "httponly": http_only,
        "secure": COOKIE_SECURE,
        "samesite": COOKIE_SAMESITE,
        "domain": COOKIE_DOMAIN,
        "path": "/",
        **({"max_age": max_age} if max_age is not None else {}),
    }


def _get_base_url() -> str:
    """
    APP_BASE_URL を正として base URL を返す。
    Hostヘッダ偽装や、127.0.0.1 / localhost 混在でのCookie問題を避けるため、
    request.host と APP_BASE_URL の host:port が一致しない場合は例外にする。
    """
    # 本番は APP_BASE_URL 必須（Host偽装対策）
    if APP_BASE_URL:
        parsed = urlparse(APP_BASE_URL)
        expected_host = parsed.netloc
        if not expected_host:
            raise RuntimeError("APP_BASE_URL is invalid")
        if request.host != expected_host:
            raise RuntimeError(
                f"Host mismatch: expected={expected_host} actual={request.host}"
            )
        return APP_BASE_URL

    # ローカル開発のみ: 127.0.0.1 / localhost に限定して動的に採用
    if request.host in {"127.0.0.1:8050", "localhost:8050"}:
        return f"{request.scheme}://{request.host}".rstrip("/")

    raise RuntimeError("APP_BASE_URL is not set")


def _build_authorize_url(state: str, base_url: str) -> str:
    redirect_uri = f"{base_url}/auth/callback"
    params = {
        "provider": "google",
        "redirect_to": redirect_uri,
        "state": state,
        # PKCE は /auth/login で付与する（code_challenge）
    }
    return f"{SUPABASE_URL}/auth/v1/authorize?{urllib.parse.urlencode(params)}"


def _supabase_auth_post(path: str, payload: dict) -> requests.Response:
    """Supabase Auth REST API 呼び出し（POST）。"""
    url = f"{SUPABASE_URL}{path}"
    headers = {
        "apikey": PUBLISHABLE_KEY,
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
        client = get_user_client(access_token)
        if not client:
            return None
        result = client.auth.get_user(access_token)
        user = getattr(result, "user", None)
        return user
    except Exception:
        return None


def _is_public_path(path: str) -> bool:
    return path.startswith(
        (
            "/auth/login",
            "/auth/callback",
            "/auth/session",
            "/auth/logout",
            "/auth/email/signin",
            "/auth/email/signup",
            "/auth/email/reset",
            "/oauth/consent",
            "/assets/",
            "/static/",
            "/_dash-component-suites/",
            "/_dash-layout",
            "/_dash-dependencies",
            "/_favicon.ico",
        )
    ) or path in {"/login", "/auth/login", "/auth/callback"}


# Flask app
flask_app = Flask(__name__)


def _safe_redirect_target(base_url: str, target: Optional[str]) -> str:
    """外部リダイレクトを防ぎつつ、指定がなければ / に戻す。"""
    if not target:
        return "/"

    parsed = urlparse(target)
    # 絶対URLの場合は同一ホストのみ許可
    if parsed.scheme or parsed.netloc:
        base_host = urlparse(base_url).netloc
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


@flask_app.before_request
def _require_auth():
    # OAuth state エラー時は自動再試行させず、その場で説明を返す
    if request.args.get("error_code") == "bad_oauth_state":
        resp = make_response(
            render_template_string(
                """
                <!doctype html>
                <html>
                  <head><meta charset="utf-8"><title>Auth error</title></head>
                  <body style="font-family:sans-serif; max-width:640px; margin:40px auto;">
                    <h2>ログインに失敗しました</h2>
                    <p>原因: OAuth state が一致しませんでした（bad_oauth_state）。</p>
                    <ul>
                      <li>複数タブで同時にログインを開始した</li>
                      <li>ブラウザ拡張/プライバシー設定で Cookie がブロックされた</li>
                      <li>前回のログイン途中で戻る/更新した</li>
                    </ul>
                    <p>対処: Cookie を削除し、タブを1つにして再試行してください。</p>
                    <p><a href="/login">ログイン画面へ戻る</a></p>
                  </body>
                </html>
                """
            ),
            400,
        )
        # state / verifier を破棄して再試行をクリア
        resp.set_cookie(STATE_COOKIE, "", **_cookie_kwargs(http_only=False, max_age=0))
        resp.set_cookie(
            CODE_VERIFIER_COOKIE, "", **_cookie_kwargs(http_only=True, max_age=0)
        )
        resp.set_cookie(REDIRECT_COOKIE, "", **_cookie_kwargs(http_only=False, max_age=0))
        return resp

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

    # 認証済み: g にセット（services 側で利用）
    g.user_id = getattr(user, "id", None)
    g.access_token = access_token
    return None


@flask_app.get("/login")
def login_page():
    return render_template_string(
        """
        <!doctype html>
        <html>
          <head><meta charset="utf-8"><title>Login</title></head>
          <body style="font-family:sans-serif; max-width:520px; margin:40px auto;">
            <h2>ログイン</h2>
            <p>Google または メール/パスワードでログインできます。</p>

            <div style="margin:16px 0;">
              <a href="/auth/login"
                 style="padding:10px 16px; background:#0070f3; color:#fff; text-decoration:none; border-radius:4px; display:inline-block;">
                 Googleでログイン
              </a>
            </div>

            <hr style="margin:24px 0;">

            <h3 style="margin-bottom:8px;">メールでログイン</h3>
            <form id="signin-form" style="display:flex; flex-direction:column; gap:8px; max-width:360px;">
              <label>メールアドレス<input type="email" name="email" required style="width:100%; padding:6px;"></label>
              <label>パスワード<input type="password" name="password" required style="width:100%; padding:6px;"></label>
              <button type="submit" style="padding:10px; background:#0070f3; color:#fff; border:none; border-radius:4px;">メールでログイン</button>
            </form>
            <div id="signin-msg" style="margin-top:8px; min-height:20px; color:#d00;"></div>

            <div style="margin-top:24px;">
              <h4 style="margin-bottom:6px;">新規登録</h4>
              <form id="signup-form" style="display:flex; flex-direction:column; gap:8px; max-width:360px;">
                <label>メールアドレス<input type="email" name="email" required style="width:100%; padding:6px;"></label>
                <label>パスワード<input type="password" name="password" required style="width:100%; padding:6px;"></label>
                <button type="submit" style="padding:10px; background:#0a7; color:#fff; border:none; border-radius:4px;">登録して確認メールを送る</button>
              </form>
              <div id="signup-msg" style="margin-top:8px; min-height:20px; color:#d00;"></div>
            </div>

            <div style="margin-top:24px;">
              <h4 style="margin-bottom:6px;">パスワードリセット</h4>
              <form id="reset-form" style="display:flex; flex-direction:column; gap:8px; max-width:360px;">
                <label>メールアドレス<input type="email" name="email" required style="width:100%; padding:6px;"></label>
                <button type="submit" style="padding:10px; background:#555; color:#fff; border:none; border-radius:4px;">リセットメールを送信</button>
              </form>
              <div id="reset-msg" style="margin-top:8px; min-height:20px; color:#d00;"></div>
            </div>

            <script>
              const postJson = async (url, body) => {
                const res = await fetch(url, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  credentials: "include",
                  body: JSON.stringify(body || {})
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                  const msg = data.message || data.error || (data.detail && data.detail.message) || "エラーが発生しました";
                  throw new Error(msg);
                }
                return data;
              };

              const setMsg = (id, msg, ok) => {
                const el = document.getElementById(id);
                if (!el) return;
                el.style.color = ok ? "#0a7" : "#d00";
                el.textContent = msg || "";
              };

              document.getElementById("signin-form").addEventListener("submit", async (e) => {
                e.preventDefault();
                setMsg("signin-msg", "");
                const form = e.target;
                const email = form.email.value.trim();
                const password = form.password.value;
                try {
                  await postJson("/auth/email/signin", { email, password });
                  setMsg("signin-msg", "ログイン成功しました。トップへ遷移します…", true);
                  window.location.href = "/";
                } catch (err) {
                  setMsg("signin-msg", err.message);
                }
              });

              document.getElementById("signup-form").addEventListener("submit", async (e) => {
                e.preventDefault();
                setMsg("signup-msg", "");
                const form = e.target;
                const email = form.email.value.trim();
                const password = form.password.value;
                try {
                  const res = await postJson("/auth/email/signup", { email, password });
                  setMsg("signup-msg", res.message || "確認メールを送信しました。受信箱を確認してください。", true);
                } catch (err) {
                  setMsg("signup-msg", err.message);
                }
              });

              document.getElementById("reset-form").addEventListener("submit", async (e) => {
                e.preventDefault();
                setMsg("reset-msg", "");
                const form = e.target;
                const email = form.email.value.trim();
                try {
                  const res = await postJson("/auth/email/reset", { email });
                  setMsg("reset-msg", res.message || "リセットメールを送信しました。", true);
                } catch (err) {
                  setMsg("reset-msg", err.message);
                }
              });
            </script>
          </body>
        </html>
        """
    )


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _exchange_code_for_session(code: str, code_verifier: str) -> dict:
    """
    Supabase Auth の token エンドポイントで code を交換（PKCE）。
    """
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=pkce"
    headers = {
        "apikey": PUBLISHABLE_KEY,
        "Content-Type": "application/json",
    }
    resp = requests.post(
        url,
        json={"auth_code": code, "code_verifier": code_verifier},
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


@flask_app.get("/auth/login")
def auth_login():
    if not SUPABASE_URL:
        return (
            "PUBLIC_SUPABASE_URL が未設定です。.env の設定を確認してください。",
            500,
        )
    try:
        base_url = _get_base_url()
    except Exception as exc:
        return (
            f"ローカルURL不一致です。ブラウザは APP_BASE_URL に統一してください。（{exc}）",
            400,
        )
    state = secrets.token_urlsafe(32)
    verifier = _pkce_verifier()
    challenge = _pkce_challenge(verifier)
    redirect_to_param = request.args.get("redirect_to", "/")
    redirect_to = _safe_redirect_target(base_url, redirect_to_param)

    # authorize URL に code_challenge を付与
    url = _build_authorize_url(state, base_url)
    url = f"{url}&code_challenge={challenge}&code_challenge_method=S256"

    resp = make_response(redirect(url))
    # state / redirect は JS から見えても機密でないため HttpOnly=False
    resp.set_cookie(STATE_COOKIE, state, **_cookie_kwargs(http_only=False, max_age=600))
    resp.set_cookie(
        REDIRECT_COOKIE, redirect_to, **_cookie_kwargs(http_only=False, max_age=600)
    )
    # code_verifier は秘密なので HttpOnly
    resp.set_cookie(
        CODE_VERIFIER_COOKIE, verifier, **_cookie_kwargs(http_only=True, max_age=600)
    )
    return resp


@flask_app.get("/auth/callback")
def auth_callback():
    try:
        _ = _get_base_url()
    except Exception as exc:
        return (
            f"ローカルURL不一致です。ブラウザは APP_BASE_URL に統一してください。（{exc}）",
            400,
        )
    code = request.args.get("code")
    verifier = request.cookies.get(CODE_VERIFIER_COOKIE)
    state_cookie = request.cookies.get(STATE_COOKIE)
    state_param = request.args.get("state")

    if not code:
        return (
            "No authorization code returned. ブラウザのCookieや拡張機能を確認してください。",
            400,
        )
    if not verifier:
        return "Missing PKCE verifier cookie.", 400
    if not state_param or not state_cookie:
        return "Missing state. Please retry login.", 400
    if state_param != state_cookie:
        return "State mismatch. Please retry login.", 400

    try:
        session = _exchange_code_for_session(code, verifier)
    except Exception as exc:  # pragma: no cover
        return f"Failed to exchange code: {exc}", 400

    access_token = session.get("access_token")
    refresh_token = session.get("refresh_token")
    expires_in = session.get("expires_in")
    if not access_token:
        return f"No access_token in session response: {session}", 400

    redirect_to_cookie = request.cookies.get(REDIRECT_COOKIE)
    base_url = _get_base_url()
    redirect_to = _safe_redirect_target(base_url, redirect_to_cookie)

    resp = make_response(redirect(redirect_to))
    _set_session_cookies(resp, access_token, refresh_token, expires_in)
    # state / verifier を破棄
    resp.set_cookie(STATE_COOKIE, "", **_cookie_kwargs(http_only=False, max_age=0))
    resp.set_cookie(
        CODE_VERIFIER_COOKIE, "", **_cookie_kwargs(http_only=True, max_age=0)
    )
    resp.set_cookie(REDIRECT_COOKIE, "", **_cookie_kwargs(http_only=False, max_age=0))
    return resp


@flask_app.post("/auth/session")
def auth_session():
    try:
        _ = _get_base_url()
    except Exception as exc:
        return (
            f"ローカルURL不一致です。ブラウザは APP_BASE_URL に統一してください。（{exc}）",
            400,
        )
    data = request.get_json(silent=True) or {}
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")

    if not access_token:
        return jsonify({"error": "missing access_token"}), 400

    user = _verify_token(access_token)
    if not user:
        return jsonify({"error": "invalid token"}), 401

    resp = make_response(jsonify({"ok": True}))
    _set_session_cookies(resp, access_token, refresh_token, expires_in)
    # state cookie を削除
    resp.set_cookie(STATE_COOKIE, "", **_cookie_kwargs(http_only=False, max_age=0))
    resp.set_cookie(REDIRECT_COOKIE, "", **_cookie_kwargs(http_only=False, max_age=0))
    return resp


@flask_app.post("/auth/email/signin")
def auth_email_signin():
    """メール/パスワードでサインインし、HttpOnly Cookie にセッションを設定する。"""
    try:
        _ = _get_base_url()
    except Exception as exc:
        return (
            jsonify({"error": "invalid_host", "message": str(exc)}),
            400,
        )

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "validation", "message": "email と password は必須です"}), 400

    try:
        resp = _supabase_auth_post(
            "/auth/v1/token?grant_type=password",
            {"email": email, "password": password},
        )
    except Exception as exc:  # システムエラー
        return jsonify({"error": "server_error", "message": str(exc)}), 500

    if resp.status_code >= 400:
        # 業務エラーとして 400 を返却（例: invalid_credentials）
        try:
            detail = resp.json()
        except Exception:
            detail = {"message": resp.text}
        return jsonify({"error": "auth_failed", "detail": detail}), 400

    session = resp.json()
    access_token = session.get("access_token")
    refresh_token = session.get("refresh_token")
    expires_in = session.get("expires_in")
    if not access_token:
        return (
            jsonify({"error": "auth_failed", "detail": session}),
            400,
        )

    resp_out = make_response(jsonify({"ok": True}))
    _set_session_cookies(resp_out, access_token, refresh_token, expires_in)
    # state / redirect をクリア（念のため）
    resp_out.set_cookie(STATE_COOKIE, "", **_cookie_kwargs(http_only=False, max_age=0))
    resp_out.set_cookie(
        CODE_VERIFIER_COOKIE, "", **_cookie_kwargs(http_only=True, max_age=0)
    )
    resp_out.set_cookie(REDIRECT_COOKIE, "", **_cookie_kwargs(http_only=False, max_age=0))
    return resp_out


@flask_app.post("/auth/email/signup")
def auth_email_signup():
    """メール/パスワードでサインアップ。メール確認が完了するまでセッションは発行しない。"""
    try:
        base_url = _get_base_url()
    except Exception as exc:
        return (
            jsonify({"error": "invalid_host", "message": str(exc)}),
            400,
        )

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "validation", "message": "email と password は必須です"}), 400

    payload = {
        "email": email,
        "password": password,
        "data": {},
        # 確認メール後のリダイレクト先（Site URL と整合すること）
        "redirect_to": f"{base_url}/login",
    }
    try:
        resp = _supabase_auth_post("/auth/v1/signup", payload)
    except Exception as exc:  # システムエラー
        return jsonify({"error": "server_error", "message": str(exc)}), 500

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = {"message": resp.text}
        return jsonify({"error": "signup_failed", "detail": detail}), 400

    # サインアップ時点ではメール確認を要求し、セッションは設定しない
    return jsonify(
        {
            "ok": True,
            "message": "サインアップしました。メールの確認リンクを開いてからサインインしてください。",
        }
    )


@flask_app.post("/auth/email/reset")
def auth_email_reset():
    """パスワードリセットメールを送信する。"""
    try:
        base_url = _get_base_url()
    except Exception as exc:
        return (
            jsonify({"error": "invalid_host", "message": str(exc)}),
            400,
        )

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    if not email:
        return jsonify({"error": "validation", "message": "email は必須です"}), 400

    payload = {
        "email": email,
        "redirect_to": f"{base_url}/login",
    }
    try:
        resp = _supabase_auth_post("/auth/v1/recover", payload)
    except Exception as exc:  # システムエラー
        return jsonify({"error": "server_error", "message": str(exc)}), 500

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = {"message": resp.text}
        return jsonify({"error": "reset_failed", "detail": detail}), 400

    return jsonify({"ok": True, "message": "パスワードリセット用メールを送信しました。"})


@flask_app.post("/auth/logout")
def auth_logout():
    resp = make_response(jsonify({"ok": True}))
    _clear_session_cookies(resp)
    return resp


# ---- OAuth 2.1 Authorization Path (consent UI) ----


@flask_app.get("/oauth/consent")
def oauth_consent():
    if not SUPABASE_URL:
        return (
            "PUBLIC_SUPABASE_URL が未設定です。.env の設定を確認してください。",
            500,
        )
    try:
        _ = _get_base_url()
    except Exception as exc:
        return (
            f"ローカルURL不一致です。ブラウザは APP_BASE_URL に統一してください。（{exc}）",
            400,
        )
    # Supabaseから渡されるクエリをそのまま承認リクエストに引き継ぐ
    # 型チェッカー対策: to_dict(flat=False) を使い、値は先頭要素を採用する
    raw_params = request.args.to_dict(flat=False)
    params = {
        k: (v[0] if isinstance(v, list) and v else "") for k, v in raw_params.items()
    }
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    scope = params.get("scope", "")
    state = params.get("state", "")
    code_challenge = params.get("code_challenge", "")
    response_type = params.get("response_type", "code")

    # 承認/拒否ボタンで Supabase authorize に送り返す
    approve_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": response_type,
        "state": state,
        "scope": scope,
        "code_challenge": code_challenge,
        "code_challenge_method": params.get("code_challenge_method", "S256"),
    }
    approve_url = (
        f"{SUPABASE_URL}/auth/v1/authorize?{urllib.parse.urlencode(approve_params)}"
    )

    deny_params = {"error": "access_denied", "state": state}
    deny_url = (
        f"{redirect_uri}?{urllib.parse.urlencode(deny_params)}" if redirect_uri else "/"
    )

    html = """
    <!doctype html>
    <html>
      <head><meta charset="utf-8"><title>Consent</title></head>
      <body style="font-family: sans-serif; max-width: 520px; margin: 40px auto;">
        <h2>アプリへのアクセスを許可しますか？</h2>
        <p>Client ID: {{client_id}}</p>
        <p>Scope: {{scope}}</p>
        <div style="margin-top:20px; display:flex; gap:10px;">
          <a href="{{approve_url}}" style="padding:10px 16px; background:#0070f3; color:#fff; text-decoration:none; border-radius:4px;">許可</a>
          <a href="{{deny_url}}" style="padding:10px 16px; background:#ccc; color:#000; text-decoration:none; border-radius:4px;">拒否</a>
        </div>
      </body>
    </html>
    """
    return render_template_string(
        html,
        client_id=client_id,
        scope=scope,
        approve_url=approve_url,
        deny_url=deny_url,
    )


# Dash を Flask にマウント
dash_app = create_app(server=flask_app)
app = dash_app.server  # for compatibility (gunicorn etc.)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    dash_app.run(host="0.0.0.0", port=port)
