"""Try the Demo: one click makes a private demo account full of example
tasks, and logs you in.

Every visitor gets their own copy, so nobody can spoil the demo for the
next person. Demo accounts have a random password nobody knows, and are
deleted a day after they're made.
"""
import secrets
from datetime import timedelta

from flask import Blueprint, flash, redirect, url_for
from werkzeug.security import generate_password_hash

from .auth import log_in
from .db import get_db
from .recurrence import first_due
from .tasks import today

bp = Blueprint("demo", __name__)

DEMO_LIFETIME = "-1 day"  # for SQLite's datetime(): how long a demo account lasts

# The example lists: name -> color.
DEMO_LISTS = {"Work": "blue", "Home": "teal", "Errands": "orange", "School": "pink", "Health": "green"}

# The example tasks. "days" is the due date counted from today (None = no
# date); the other keys are columns of the tasks table.
DEMO_TASKS = [
    {"title": "Finish thesis chapter 2", "emoji": "📚", "list": "School", "days": 1, "due_time": "20:00",
     "priority": 1, "remind_before": 0, "tags": ["urgent"]},
    {"title": "Buy eggs, milk and rice", "emoji": "🛒", "list": "Errands", "days": 0, "due_time": "18:00",
     "remind_before": 0, "tags": ["groceries"]},
    {"title": "Team standup", "emoji": "💼", "list": "Work", "days": 0, "due_time": "09:30", "repeat": "weekdays"},
    {"title": "Send status report", "list": "Work", "days": 3, "due_time": "17:00", "doing": 1, "tags": ["reports"]},
    {"title": "Vitamins", "emoji": "💊", "list": "Health", "days": 0, "due_time": "08:00", "repeat": "day:1"},
    {"title": "Gym", "emoji": "💪", "list": "Health", "repeat": "week:1:0", "due_time": "06:00"},
    {"title": "Pack for the trip", "emoji": "✈️", "list": "Home", "days": 4, "due_time": "05:30",
     "description": "Flight at 6am. Leave by 3:30, grab coffee at the airport.",
     "subtasks": [("Passport", 1), ("Phone charger", 1), ("Sunscreen", 0), ("Swimsuit", 0), ("Snacks for the plane", 0)]},
    {"title": "Call grandma", "emoji": "📞", "days": 5, "due_time": "15:00", "tags": ["family"]},
    {"title": "Renew library card", "list": "Errands", "days": -2},  # already late
    {"title": "Plan Mia's birthday party", "emoji": "🎉", "list": "Home", "days": 18, "tags": ["family"]},
    {"title": "Book dentist", "days": 7},
]
# Done in the last few days, so the demo shows a streak and a busy week.
DEMO_DONE = [("Water the plants", 0), ("Morning run", 0), ("Clean the kitchen", 1),
             ("Submit essay", 2), ("Fix bike tire", 3), ("Call the bank", 4)]

TASK_COLUMNS = ["title", "description", "due_time", "repeat", "remind_before", "priority", "emoji", "doing"]


def delete_old_demos(db):
    """Delete demo accounts older than a day, with everything in them."""
    old = [row["id"] for row in db.execute(
        "SELECT id FROM users WHERE is_demo = 1 AND created_at < datetime('now', 'localtime', ?)",
        (DEMO_LIFETIME,),
    )]
    for user_id in old:
        # Rows that point to other rows go first: tag links and subtasks
        # point to tasks, and everything points to the user.
        task_ids = "SELECT id FROM tasks WHERE user_id = ?"
        db.execute(f"DELETE FROM task_tags WHERE task_id IN ({task_ids})", (user_id,))
        db.execute(f"DELETE FROM subtasks WHERE task_id IN ({task_ids})", (user_id,))
        for table in ["tasks", "tags", "lists", "undo"]:
            db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))


def add_demo_data(db, user_id, now):
    """Fill a new demo account with the example lists and tasks."""
    list_ids = {}
    for name, color in DEMO_LISTS.items():
        cursor = db.execute("INSERT INTO lists (user_id, name, color) VALUES (?, ?, ?)", (user_id, name, color))
        list_ids[name] = cursor.lastrowid

    for example in DEMO_TASKS:
        if "days" in example:
            due = (now + timedelta(days=example["days"])).isoformat()
        else:
            # A repeating task without a date starts on its first day, like
            # "every Monday" starting on the coming Monday.
            due = first_due(example["repeat"], now).isoformat() if example.get("repeat") else None
        values = [example.get(column) for column in TASK_COLUMNS]
        values[TASK_COLUMNS.index("description")] = example.get("description", "")
        values[TASK_COLUMNS.index("priority")] = example.get("priority", 0)
        values[TASK_COLUMNS.index("doing")] = example.get("doing", 0)
        cursor = db.execute(
            f"INSERT INTO tasks (user_id, list_id, due_date, {', '.join(TASK_COLUMNS)})"
            f" VALUES (?, ?, ?, {', '.join('?' for _ in TASK_COLUMNS)})",
            [user_id, list_ids.get(example.get("list")), due, *values],
        )
        task_id = cursor.lastrowid
        for name in example.get("tags", []):
            db.execute("INSERT OR IGNORE INTO tags (user_id, name) VALUES (?, ?)", (user_id, name))
            tag_id = db.execute("SELECT id FROM tags WHERE user_id = ? AND name = ?", (user_id, name)).fetchone()["id"]
            db.execute("INSERT INTO task_tags (task_id, tag_id) VALUES (?, ?)", (task_id, tag_id))
        for title, done in example.get("subtasks", []):
            db.execute("INSERT INTO subtasks (task_id, title, done) VALUES (?, ?, ?)", (task_id, title, done))

    for title, days_ago in DEMO_DONE:
        db.execute(
            "INSERT INTO tasks (user_id, title, completed, completed_at) VALUES (?, ?, 1, ?)",
            (user_id, title, f"{now - timedelta(days=days_ago)} 09:00:00"),
        )


@bp.post("/demo")
def start():
    """Make a fresh demo account, fill it with examples, and log in."""
    db = get_db()
    delete_old_demos(db)
    # A random name and password: nobody can log in to it again later.
    username = f"demo_{secrets.token_hex(3)}"
    cursor = db.execute(
        "INSERT INTO users (username, password_hash, display_name, avatar, is_demo)"
        " VALUES (?, ?, 'Demo', '🦊', 1)",
        (username, generate_password_hash(secrets.token_urlsafe(16))),
    )
    add_demo_data(db, cursor.lastrowid, today())
    db.commit()
    log_in(cursor.lastrowid)
    flash("Welcome to the demo! Change anything you like. This demo account is deleted after a day.")
    return redirect(url_for("tasks.index"))
