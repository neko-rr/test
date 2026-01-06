import os
from flask import g
from werkzeug.local import LocalProxy
from supabase import create_client
from supabase.client import Client
from flask_storage import FlaskSessionStorage

url = os.environ.get("SUPABASE_URL", "")
key = os.environ.get("SUPABASE_KEY", "")

def get_supabase() -> Client:
    if "supabase" not in g:
        # supabase==2.0.0 では flow_type 引数が無いため、storage のみ指定
        g.supabase = create_client(
            url,
            key,
            options={"storage": FlaskSessionStorage()},
        )
    return g.supabase

supabase: Client = LocalProxy(get_supabase)

