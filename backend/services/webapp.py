"""Production wiring: optional password gate and CORS allow-list (the static UI is served by server.py).

* APP_PASSWORD   - when set, every page and API call needs a login (cookie). Leave unset for local dev.
* CORS_ORIGINS   - comma-separated origins allowed to call the API from another site (default: none).
"""
from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

COOKIE = "sc_session"
OPEN_PATHS = {"/login", "/logout", "/api/health"}

LOGIN_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in · Disruption Assistant</title>
<style>
:root{color-scheme:light}body{margin:0;min-height:100vh;display:grid;place-items:center;background:linear-gradient(135deg,#eff6ff,#ecfeff);font-family:Inter,system-ui,sans-serif;color:#0f172a}
form{width:min(360px,92vw);background:#fff;border:1px solid #e4e9f1;border-radius:18px;padding:28px;box-shadow:0 12px 32px rgba(15,23,42,.1)}
.logo{width:44px;height:44px;border-radius:13px;background:linear-gradient(135deg,#2563eb,#06b6d4);margin-bottom:14px}
h1{font-size:1.25rem;margin:0 0 4px}p{margin:0 0 18px;color:#526075;font-size:.9rem}
input{width:100%;box-sizing:border-box;padding:11px 12px;border:1px solid #dbe2ec;border-radius:10px;font-size:.95rem}
button{margin-top:12px;width:100%;padding:11px;border:0;border-radius:10px;background:#2563eb;color:#fff;font-weight:600;font-size:.95rem;cursor:pointer}
.err{color:#b91c1c;font-size:.85rem;margin-top:10px}
</style></head><body><form method="post" action="/login"><div class="logo"></div>
<h1>Supply-Chain Disruption Assistant</h1><p>Enter the access password to continue.</p>
<input type="password" name="password" placeholder="Password" autofocus required>
<button type="submit">Sign in</button>{error}</form></body></html>"""


def _token(password: str) -> str:
    return hmac.new(password.encode(), b"supplychain-session-v1", hashlib.sha256).hexdigest()


def install(app: FastAPI) -> None:
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

    password = os.getenv("APP_PASSWORD", "")
    if password:
        good = _token(password)

        @app.middleware("http")
        async def gate(request: Request, call_next):
            path = request.url.path
            if path in OPEN_PATHS or path.startswith("/static/") or path.endswith((".svg", ".ico")):
                return await call_next(request)
            if hmac.compare_digest(request.cookies.get(COOKIE, ""), good):
                return await call_next(request)
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Sign in required"}, status_code=401)
            return RedirectResponse("/login", status_code=303)

        def _secure(request: Request) -> bool:
            return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"

        @app.get("/login", include_in_schema=False)
        def login_page():
            return HTMLResponse(LOGIN_HTML.replace("{error}", ""))

        @app.post("/login", include_in_schema=False)
        def login(request: Request, password_in: str = Form(..., alias="password")):
            if not hmac.compare_digest(_token(password_in), good):
                return HTMLResponse(LOGIN_HTML.replace("{error}", '<div class="err">Wrong password.</div>'), status_code=401)
            r = RedirectResponse("/", status_code=303)
            secure = _secure(request)
            # SameSite=None lets the app work when embedded in another site over HTTPS
            r.set_cookie(COOKIE, good, httponly=True, secure=secure, samesite="none" if secure else "lax", max_age=60 * 60 * 24 * 14)
            return r

        @app.get("/logout", include_in_schema=False)
        def logout():
            r = RedirectResponse("/login", status_code=303)
            r.delete_cookie(COOKIE)
            return r
