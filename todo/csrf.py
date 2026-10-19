"""Protection against cross-site request forgery (CSRF).

Without this, another website could hide a form that POSTs to
/tasks/1/delete, and your browser would send it with your cookies.
The fix: keep a random token in the session and put the same token in
every form. A POST whose token doesn't match the session's is refused.
"""
import secrets

from flask import abort, request, session


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def check_csrf():
    if request.method != "POST":
        return
    expected = session.get("csrf_token")
    sent = request.form.get("csrf_token", "")
    # compare_digest takes the same time whether the tokens match early or
    # late, so an attacker can't guess the token from response times.
    if not expected or not secrets.compare_digest(sent.encode(), expected.encode()):
        abort(400, "The form expired or came from another site. Reload the page and try again.")


def init_app(app):
    app.before_request(check_csrf)
    # Lets every template call {{ csrf_token() }}.
    app.jinja_env.globals["csrf_token"] = csrf_token
