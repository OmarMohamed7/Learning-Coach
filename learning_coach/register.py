"""Sign-up page for the Chainlit app, served at /register on Chainlit's own server."""
from html import escape

from chainlit.server import app
from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import register_user

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Create account</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0f0f10;color:#eee;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
form{{background:#1a1a1c;padding:2rem;border-radius:12px;width:min(340px,90vw);display:flex;flex-direction:column;gap:.9rem}}
h1{{font-size:1.25rem;margin:0}} label{{font-size:.85rem;display:flex;flex-direction:column;gap:.3rem}}
input{{padding:.6rem;border-radius:8px;border:1px solid #333;background:#0f0f10;color:#eee}}
button{{padding:.65rem;border:0;border-radius:8px;background:#e5484d;color:#fff;font-weight:600;cursor:pointer}}
.err{{color:#ff8b8b;font-size:.85rem}} a{{color:#8ab4ff;font-size:.85rem}}
</style></head><body>
<form method="post" action="/register">
<h1>Create account</h1>{error}
<label>Username<input name="username" value="{username}" required minlength="3" maxlength="32" autocomplete="username"></label>
<label>Password<input name="password" type="password" required minlength="8" autocomplete="new-password"></label>
<label>Confirm password<input name="confirm" type="password" required minlength="8" autocomplete="new-password"></label>
<button type="submit">Register</button>
<a href="/login">Already have an account? Sign in</a>
</form></body></html>"""


def _page(error: str = "", username: str = "", status: int = 200) -> HTMLResponse:
    err = f'<div class="err">{escape(error)}</div>' if error else ""
    return HTMLResponse(_PAGE.format(error=err, username=escape(username)), status_code=status)


async def _show_form():
    return _page()


async def _submit(username: str = Form(...), password: str = Form(...), confirm: str = Form(...)):
    if password != confirm:
        return _page("Passwords do not match.", username, 400)
    error = await register_user(username, password)
    if error:
        return _page(error, username, 400)
    return RedirectResponse("/login", status_code=303)


# Chainlit's catch-all route is already registered; ours must sit in front of it.
_before = len(app.router.routes)
app.add_api_route("/register", _show_form, methods=["GET"], include_in_schema=False)
app.add_api_route("/register", _submit, methods=["POST"], include_in_schema=False)
_ours = app.router.routes[_before:]
del app.router.routes[_before:]
app.router.routes[0:0] = _ours
