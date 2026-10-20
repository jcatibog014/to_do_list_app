"""Lists (projects) like Work or Home: the Lists page, and making,
renaming, coloring and deleting lists.

The task helpers (user_lists(), get_list_or_404(), go_back()...) come from
tasks.py, so both files check ownership the same way.
"""
import sqlite3

from flask import Blueprint, g, redirect, render_template, request, url_for

from .auth import require_login
from .db import get_db
from .tasks import get_list_or_404, go_back, notify, user_lists
from .validation import (
    LIST_COLORS,
    LIST_NAME_MAX,
    capitalize_first,
    next_list_color,
    validate_list_color,
    validate_list_name,
)

bp = Blueprint("lists", __name__)
bp.before_request(require_login)


@bp.get("/lists")
def index():
    """Every list as a card, with how many tasks are open and done."""
    db = get_db()
    # GROUP BY makes one row per list. SUM(...) adds up the 1s and 0s of
    # "completed = 0", which counts the open tasks. LEFT JOIN keeps lists
    # that have no tasks yet (their counts come out as NULL, so COALESCE
    # turns NULL into 0).
    lists = db.execute(
        "SELECT lists.*, COALESCE(SUM(tasks.completed = 0), 0) AS open_count,"
        " COALESCE(SUM(tasks.completed = 1), 0) AS done_count"
        " FROM lists LEFT JOIN tasks ON tasks.list_id = lists.id"
        " WHERE lists.user_id = ? GROUP BY lists.id ORDER BY lists.name",
        (g.user["id"],),
    ).fetchall()
    inbox = db.execute(
        "SELECT COALESCE(SUM(completed = 0), 0) AS open_count, COALESCE(SUM(completed = 1), 0) AS done_count"
        " FROM tasks WHERE user_id = ? AND list_id IS NULL",
        (g.user["id"],),
    ).fetchone()
    return render_template(
        "lists.html", lists=lists, inbox=inbox, list_colors=LIST_COLORS,
        list_name_max=LIST_NAME_MAX, next_color=next_list_color(len(lists)),
    )


@bp.post("/lists/new")
def create():
    name, error = validate_list_name(request.form)
    color, color_error = validate_list_color(request.form, default=next_list_color(len(user_lists())))
    error = error or color_error
    if error is None:
        db = get_db()
        try:
            cursor = db.execute(
                "INSERT INTO lists (user_id, name, color) VALUES (?, ?, ?)",
                (g.user["id"], name, color),
            )
            db.commit()
        except sqlite3.IntegrityError:
            # The UNIQUE (user_id, name) rule in schema.sql refused it.
            error = f"You already have a list called “{name}”."
        else:
            notify(f"Made the list “{name}”.")
            if request.values.get("next") == "lists":
                return redirect(url_for("lists.index"))
            return redirect(url_for("tasks.index", list=cursor.lastrowid))
    notify(error, "error")
    return go_back()


@bp.post("/lists/<int:list_id>/rename")
def rename(list_id):
    found = get_list_or_404(list_id)
    name, error = validate_list_name(request.form)
    if error is None:
        db = get_db()
        try:
            db.execute("UPDATE lists SET name = ? WHERE id = ?", (name, list_id))
            db.commit()
        except sqlite3.IntegrityError:
            error = f"You already have a list called “{name}”."
        else:
            notify(f"Renamed “{capitalize_first(found['name'])}” to “{name}”.")
    if error:
        notify(error, "error")
    return go_back()


@bp.post("/lists/<int:list_id>/color")
def change_color(list_id):
    found = get_list_or_404(list_id)
    color, error = validate_list_color(request.form)
    if error:
        notify(error, "error")
    else:
        db = get_db()
        db.execute("UPDATE lists SET color = ? WHERE id = ?", (color, list_id))
        db.commit()
        notify(f"“{capitalize_first(found['name'])}” is {color} now.")
    return go_back()


@bp.post("/lists/<int:list_id>/delete")
def delete(list_id):
    found = get_list_or_404(list_id)
    db = get_db()
    # Keep the tasks: move them to the Inbox, so none point to a missing list.
    db.execute("UPDATE tasks SET list_id = NULL WHERE list_id = ?", (list_id,))
    db.execute("DELETE FROM lists WHERE id = ?", (list_id,))
    db.commit()
    notify(f"Deleted the list “{capitalize_first(found['name'])}”. Its tasks are in the Inbox now.")
    if request.values.get("next") == "lists":
        return redirect(url_for("lists.index"))
    return redirect(url_for("tasks.index"))
