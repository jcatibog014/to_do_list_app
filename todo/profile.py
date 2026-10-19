"""The profile page: your picture, name, username, password and theme."""
import sqlite3

from flask import Blueprint, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .auth import require_login
from .db import get_db
from .pages import user_streaks
from .tasks import notify
from .validation import (
    APPEARANCES,
    AVATAR_CHOICES,
    DISPLAY_NAME_MAX,
    PASSWORD_MIN,
    THEMES,
    USERNAME_MAX,
    validate_password_change,
    validate_profile,
    validate_settings,
)

bp = Blueprint("profile", __name__)
bp.before_request(require_login)


def render_profile(info_form=None, info_errors=None, password_errors=None):
    """The profile page. With errors, it answers 400 and keeps what was typed.

    The page has three separate forms, so each one gets its own errors.
    Passwords are never sent back to the browser.
    """
    (current, best), _ = user_streaks()
    counts = get_db().execute(
        "SELECT COALESCE(SUM(completed = 1), 0) AS done, COALESCE(SUM(completed = 0), 0) AS open"
        " FROM tasks WHERE user_id = ?",
        (g.user["id"],),
    ).fetchone()
    info_form = info_form or {
        "username": g.user["username"],
        "display_name": g.user["display_name"] or "",
        "avatar": g.user["avatar"] or "",
    }
    html = render_template(
        "profile.html", info_form=info_form, info_errors=info_errors or {},
        password_errors=password_errors or {}, current=current, best=best, counts=counts,
        themes=THEMES, appearances=APPEARANCES, avatar_choices=AVATAR_CHOICES,
        username_max=USERNAME_MAX, display_name_max=DISPLAY_NAME_MAX, password_min=PASSWORD_MIN,
        member_since=g.user["created_at"][:10],
    )
    return html, 400 if info_errors or password_errors else 200


@bp.get("/profile")
def index():
    return render_profile()


@bp.post("/profile")
def update_info():
    data, errors = validate_profile(request.form)
    if not errors:
        db = get_db()
        try:
            db.execute(
                "UPDATE users SET username = ?, display_name = ?, avatar = ? WHERE id = ?",
                (data["username"], data["display_name"], data["avatar"], g.user["id"]),
            )
            db.commit()
        except sqlite3.IntegrityError:
            # The UNIQUE rule on users.username: someone else has that name.
            errors["username"] = "That username is taken. Try another one."
    if errors:
        return render_profile(info_form=request.form, info_errors=errors)
    notify("Saved your profile.")
    return redirect(url_for("profile.index"))


@bp.post("/profile/password")
def change_password():
    new_password, errors = validate_password_change(request.form)
    # Asking for the current password stops someone who finds your phone
    # unlocked from locking you out of your own account.
    current = request.form.get("current_password", "")
    if current and not check_password_hash(g.user["password_hash"], current):
        errors["current_password"] = "That isn't your current password."
    if errors:
        return render_profile(password_errors=errors)
    db = get_db()
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (generate_password_hash(new_password), g.user["id"]))
    db.commit()
    notify("Changed your password. Use the new one next time you log in.")
    return redirect(url_for("profile.index"))


@bp.post("/profile/theme")
def change_theme():
    (_, best), _ = user_streaks()
    data, errors = validate_settings(request.form, best)
    if errors:
        for message in errors.values():
            notify(message, "error")
    else:
        db = get_db()
        db.execute("UPDATE users SET theme = ?, appearance = ? WHERE id = ?",
                   (data["theme"], data["appearance"], g.user["id"]))
        db.commit()
        notify(f"Theme saved: {THEMES[data['theme']]['label']}, {APPEARANCES[data['appearance']].lower()}.")
    return redirect(url_for("profile.index") + "#theme")
