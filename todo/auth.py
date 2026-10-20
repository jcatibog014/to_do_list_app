"""Accounts: register, log in and log out.

Logging in stores the user's id in the session (a signed cookie). Before
every request, load_logged_in_user() reads it back and puts the user on
g.user, so views and templates know who is asking.
"""
import sqlite3

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .validation import PASSWORD_MIN, USERNAME_MAX, validate_registration

bp = Blueprint("auth", __name__)


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def require_login():
    """Send logged-out visitors to the login page.

    A blueprint runs it before each of its pages with
    bp.before_request(require_login), so a new page can't forget the check.
    """
    if g.user is None:
        return redirect(url_for("auth.login"))


def log_in(user_id):
    # Start a fresh session, so nothing from before logging in carries over.
    session.clear()
    session["user_id"] = user_id


@bp.route("/register", methods=["GET", "POST"])
def register():
    form, errors = {}, {}
    if request.method == "POST":
        form = request.form
        data, errors = validate_registration(form)
        if not errors:
            db = get_db()
            try:
                # generate_password_hash() turns the password into a salted
                # hash. Even someone who reads the database can't get the
                # password back from it.
                cursor = db.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (data["username"], generate_password_hash(data["password"])),
                )
                db.commit()
            except sqlite3.IntegrityError:
                # The UNIQUE rule in schema.sql refused a name that's taken.
                errors["username"] = "That username is taken. Try another one."
            else:
                log_in(cursor.lastrowid)
                flash(f"Welcome, {data['username']}! Your account is ready.")
                return redirect(url_for("tasks.index"))

    # Never send the password back to the browser, even when there are errors.
    form = {"username": form.get("username", "")}
    html = render_template(
        "register.html", form=form, errors=errors,
        username_max=USERNAME_MAX, password_min=PASSWORD_MIN,
    )
    return html, 400 if errors else 200


@bp.route("/login", methods=["GET", "POST"])
def login():
    username, error = "", None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        # One message for both mistakes, so nobody can find out which
        # usernames exist by trying them.
        if user is None or not check_password_hash(user["password_hash"], password):
            error = "Incorrect username or password."
        else:
            log_in(user["id"])
            return redirect(url_for("tasks.index"))

    html = render_template("login.html", username=username, error=error)
    return html, 400 if error else 200


# Logging out changes something, so it's a POST with a CSRF token. As a
# plain link, any other site could log you out by embedding it.
@bp.post("/logout")
def logout():
    session.clear()
    flash("You've logged out.")
    return redirect(url_for("auth.login"))
