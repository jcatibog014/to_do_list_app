"""One demo account, full of example tasks, to show the app to someone.

Make it on the server with:

    flask --app todo create-demo

It asks for a username and a password, so the password never has to be
written in the code (which is public on GitHub). Running it again puts
fresh example tasks back. The account is marked users.is_demo = 1, and
the profile page won't let anyone change its username or password, so the
login you share keeps working.
"""
from datetime import timedelta

import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from .db import get_db
from .recurrence import first_due
from .tasks import today
from .validation import password_error, username_error

# The example lists: name -> color.
DEMO_LISTS = {"Work": "blue", "Home": "teal", "Errands": "orange", "School": "pink", "Health": "green"}

# The example tasks. "days" is the due date counted from today; the other
# keys are columns of the tasks table.
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


def clear_user_data(db, user_id):
    """Delete everything a user has (tasks, lists, tags...), but keep the account."""
    # Rows that point to other rows go first: tag links and subtasks point to tasks.
    task_ids = "SELECT id FROM tasks WHERE user_id = ?"
    db.execute(f"DELETE FROM task_tags WHERE task_id IN ({task_ids})", (user_id,))
    db.execute(f"DELETE FROM subtasks WHERE task_id IN ({task_ids})", (user_id,))
    for table in ["tasks", "tags", "lists", "undo"]:
        db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))


def add_demo_data(db, user_id, now):
    """Fill the demo account with the example lists and tasks."""
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
            due = first_due(example["repeat"], now).isoformat()
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


@click.command("create-demo")
@click.option("--username", prompt="Demo username", default="demo", show_default=True)
# hide_input keeps the password off the screen, and confirmation_prompt asks twice.
@click.option("--password", prompt="Demo password", hide_input=True, confirmation_prompt=True)
@with_appcontext  # gives the command the app's config and database, like a page has
def create_demo_command(username, password):
    """Make the demo account (or refill it) with example tasks."""
    username = username.strip()
    if error := username_error(username) or password_error(password):
        raise click.UsageError(error)

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if user and not user["is_demo"]:
        # Plain quotes: some consoles can't show curly ones.
        raise click.UsageError(f'"{username}" is a real person\'s account. Pick another username for the demo.')

    if user:
        # Run again: same account, new password, and fresh example tasks.
        clear_user_data(db, user["id"])
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password), user["id"]))
        user_id = user["id"]
    else:
        cursor = db.execute(
            "INSERT INTO users (username, password_hash, display_name, avatar, is_demo)"
            " VALUES (?, ?, 'Demo', '🦊', 1)",
            (username, generate_password_hash(password)),
        )
        user_id = cursor.lastrowid
    add_demo_data(db, user_id, today())
    db.commit()
    click.echo(f'Demo account ready. Log in as "{username}" with the password you typed.')


def init_app(app):
    app.cli.add_command(create_demo_command)
