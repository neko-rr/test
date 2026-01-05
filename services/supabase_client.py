import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client

try:  # Flask が無い場合もあるため安全に import
    from flask import g, has_app_context
except Exception:  # pragma: no cover
    g = None
    has_app_context = lambda: False  # type: ignore

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOTENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(dotenv_path=DOTENV_PATH, override=False)

SUPABASE_URL = os.getenv("PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL")
PUBLISHABLE_KEY = (
    os.getenv("PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY") or os.getenv("SUPABASE_KEY")
)
SECRET_KEY = os.getenv("SUPABASE_SECRET_DEFAULT_KEY")


def _create_client(api_key: str, access_token: Optional[str] = None) -> Optional[Client]:
    if not SUPABASE_URL or not api_key:
        return None
    headers = None
    if access_token:
        headers = {"Authorization": f"Bearer {access_token}"}
    return create_client(SUPABASE_URL, api_key, options={"headers": headers} if headers else None)


@lru_cache(maxsize=1)
def get_publishable_client() -> Optional[Client]:
    """公開してよい publishable key で生成（RLS前提）。"""
    return _create_client(PUBLISHABLE_KEY or "")


def get_secret_client() -> Optional[Client]:
    """管理操作が必要なときだけ使用（漏洩注意）。"""
    return _create_client(SECRET_KEY or "")


def get_user_client(access_token: Optional[str]) -> Optional[Client]:
    """ユーザーのアクセストークンをヘッダに付与したクライアントを返す。"""
    if not access_token:
        return None
    return _create_client(PUBLISHABLE_KEY or "", access_token=access_token)


def get_supabase_client() -> Optional[Client]:
    """
    既存互換API。
    - Flaskコンテキストに access_token があればユーザークライアント
    - なければ publishable クライアント
    """
    token = None
    if has_app_context() and g is not None and hasattr(g, "access_token"):
        token = getattr(g, "access_token", None)
    user_client = get_user_client(token)
    if user_client:
        return user_client
    return get_publishable_client()
