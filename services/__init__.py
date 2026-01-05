"""
テスト用の最小構成。存在しないサービスモジュールへの依存を避ける。
認証確認に必要なのは Supabase クライアントのみ。
"""

from .supabase_client import (
    get_publishable_client,
    get_secret_client,
    get_supabase_client,
    get_user_client,
)

__all__ = [
    "get_publishable_client",
    "get_secret_client",
    "get_supabase_client",
    "get_user_client",
]
