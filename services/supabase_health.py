import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from services.supabase_client import get_supabase_client


def _mask_key(key: Optional[str]) -> str:
    if not key:
        return ""
    tail = key[-4:] if len(key) >= 4 else key
    return f"***{tail}"


def _extract_response_data(response: Any) -> List[Dict[str, Any]]:
    """supabase-py のレスポンスから data を安全に取り出す。"""
    error = getattr(response, "error", None)
    if error:
        raise RuntimeError(str(error))
    data = getattr(response, "data", None)
    return data or []


def _storage_list_objects(supabase: Any, bucket: str) -> List[Dict[str, Any]]:
    """supabase-py の list() シグネチャ差異を吸収してオブジェクト一覧を返す。"""
    storage = supabase.storage.from_(bucket)
    try:
        return storage.list(path="")
    except TypeError:
        # 古い/別バージョンのシグネチャ対策
        return storage.list()


def check_supabase_health(write: bool = False) -> Dict[str, Any]:
    """
    Supabase 接続ヘルスチェック（env/client/DB/Storage）。

    - 目的: 「繋がってる/繋がってない」ではなく、
      DBの参照がRLSで落ちているのか、0件なだけなのか、Storageが見えるのかを切り分ける。
    - 注意: ログに SUPABASE_KEY をそのまま出さない。
    """
    started_at = datetime.now(timezone.utc).isoformat()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    report: Dict[str, Any] = {
        "started_at": started_at,
        "env": {
            "SUPABASE_URL_set": bool(url),
            "SUPABASE_KEY_set": bool(key),
            "SUPABASE_KEY_masked": _mask_key(key),
        },
        "client": {"ok": False, "error": None},
        "db": {},
        "storage": {},
        "ok": False,
    }

    client = get_supabase_client()
    if client is None:
        report["client"]["ok"] = False
        report["client"]["error"] = (
            "Supabase client is None (missing env or init failed)"
        )
        report["ok"] = False
        return report

    report["client"]["ok"] = True

    # --- DB READ: theme_settings ---
    try:
        res = (
            client.table("theme_settings")
            .select("members_id,members_type_name,theme")
            .limit(1)
            .execute()
        )
        rows = _extract_response_data(res)
        report["db"]["theme_settings_select"] = {"ok": True, "rows": len(rows)}
    except Exception as exc:
        report["db"]["theme_settings_select"] = {"ok": False, "error": str(exc)}

    # --- DB READ: registration_product_information ---
    try:
        res = (
            client.table("registration_product_information")
            .select("registration_product_id,photo_id,barcode_number,creation_date")
            .order("creation_date", desc=True)
            .limit(1)
            .execute()
        )
        rows = _extract_response_data(res)
        sample = rows[0] if rows else None
        report["db"]["registration_product_information_select"] = {
            "ok": True,
            "rows": len(rows),
            "sample": sample,
        }
    except Exception as exc:
        report["db"]["registration_product_information_select"] = {
            "ok": False,
            "error": str(exc),
        }

    # --- DB READ: photo ---
    try:
        res = (
            client.table("photo")
            .select(
                "photo_id,photo_thumbnail_url,photo_high_resolution_url,photo_registration_date"
            )
            .order("photo_registration_date", desc=True)
            .limit(1)
            .execute()
        )
        rows = _extract_response_data(res)
        sample = rows[0] if rows else None
        report["db"]["photo_select"] = {"ok": True, "rows": len(rows), "sample": sample}
    except Exception as exc:
        report["db"]["photo_select"] = {"ok": False, "error": str(exc)}

    # --- STORAGE: buckets + photos bucket objects ---
    try:
        buckets = client.storage.list_buckets()
        bucket_names: List[str] = []
        for b in buckets or []:
            if isinstance(b, dict):
                name = b.get("name")
            else:
                name = getattr(b, "name", None)
            if name:
                bucket_names.append(str(name))
        report["storage"]["list_buckets"] = {
            "ok": True,
            "bucket_names": bucket_names,
        }
    except Exception as exc:
        report["storage"]["list_buckets"] = {"ok": False, "error": str(exc)}

    try:
        objects = _storage_list_objects(client, "photos")
        report["storage"]["photos_list"] = {
            "ok": True,
            "objects": len(objects or []),
            "sample_names": [
                obj.get("name")
                for obj in (objects or [])[:5]
                if isinstance(obj, dict) and obj.get("name")
            ],
        }
    except Exception as exc:
        report["storage"]["photos_list"] = {"ok": False, "error": str(exc)}

    # --- Optional DB WRITE (safe test row) ---
    if write:
        try:
            test_payload = {
                "members_id": 9998,
                "members_type_name": "healthcheck",
                "theme": "minty",
            }
            res = (
                client.table("theme_settings")
                .upsert(test_payload, on_conflict="members_id,members_type_name")
                .execute()
            )
            _extract_response_data(res)
            # Read back
            res2 = (
                client.table("theme_settings")
                .select("members_id,members_type_name,theme")
                .eq("members_id", 9998)
                .eq("members_type_name", "healthcheck")
                .limit(1)
                .execute()
            )
            rows = _extract_response_data(res2)
            report["db"]["theme_settings_write_test"] = {
                "ok": True,
                "rows": len(rows),
                "sample": rows[0] if rows else None,
            }
        except Exception as exc:
            report["db"]["theme_settings_write_test"] = {"ok": False, "error": str(exc)}

    # 総合判定: clientがOKで、DB/Storageのいずれかが致命的に落ちていないこと
    # （用途上は「どこで落ちているか」を返すのが主目的なので、ok は緩めにする）
    report["ok"] = bool(report["client"]["ok"])
    return report
