import os
from flask import Flask, render_template

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me")


@app.route("/")
def index():
    return render_template(
        "index.html",
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_anon_key=os.environ.get(
            "SUPABASE_ANON_KEY", os.environ.get("SUPABASE_KEY", "")
        ),
    )


@app.route("/auth/callback")
def auth_callback():
    return render_template(
        "callback.html",
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_anon_key=os.environ.get(
            "SUPABASE_ANON_KEY", os.environ.get("SUPABASE_KEY", "")
        ),
    )


@app.route("/logout")
def logout():
    return render_template(
        "logout.html",
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_anon_key=os.environ.get(
            "SUPABASE_ANON_KEY", os.environ.get("SUPABASE_KEY", "")
        ),
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)

