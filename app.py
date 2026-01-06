import os
from flask import Flask, redirect, request, session, render_template_string
from supabase_client import supabase

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your-secret-key-change-this-in-production")

# ホームページ
@app.route("/")
def index():
    user = None
    try:
        user = supabase.auth.get_user()
    except:
        pass
    
    if user:
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Welcome</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }
                .user-info { background: #f0f0f0; padding: 20px; border-radius: 8px; margin: 20px 0; }
                .button { background: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px; display: inline-block; }
            </style>
        </head>
        <body>
            <h1>Welcome!</h1>
            <div class="user-info">
                <p><strong>Email:</strong> {{ user.email }}</p>
                <p><strong>ID:</strong> {{ user.id }}</p>
            </div>
            <a href="/signout" class="button">Sign Out</a>
        </body>
        </html>
        """, user=user.user if hasattr(user, 'user') else user)
    else:
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Sign In</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; text-align: center; }
                .button { background: #4285f4; color: white; padding: 15px 30px; text-decoration: none; border-radius: 4px; display: inline-block; font-size: 16px; }
                .button:hover { background: #357ae8; }
            </style>
        </head>
        <body>
            <h1>Welcome to the App</h1>
            <p>Please sign in with your Google account to continue.</p>
            <a href="/signin/google" class="button">Sign in with Google</a>
        </body>
        </html>
        """)

# Google OAuth サインイン
@app.route("/signin/google")
def signin_with_google():
    res = supabase.auth.sign_in_with_oauth(
        {
            "provider": "google",
            "options": {
                "redirect_to": f"{request.host_url}callback"
            },
        }
    )
    return redirect(res.url)

# OAuth コールバック
@app.route("/callback")
def callback():
    code = request.args.get("code")
    next_url = request.args.get("next", "/")

    if code:
        res = supabase.auth.exchange_code_for_session({"auth_code": code})

    return redirect(next_url)

# サインアウト
@app.route("/signout")
def signout():
    supabase.auth.sign_out()
    return redirect("/")

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)

