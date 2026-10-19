"""Database helpers.

Each request gets one SQLite connection: get_db() opens it the first time
it's needed and keeps it on `g` (Flask's per-request storage), and
close_db() closes it when the request ends.
"""
import sqlite3

import click
from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        # Rows act like dicts, so you can write row["title"] instead of row[1].
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the tables if they don't exist yet. Safe to run again."""
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))
    add_missing_columns(db)


# Columns added to a table after it was first made, with their SQL types.
NEW_COLUMNS = {
    "tasks": {
        "user_id": "INTEGER REFERENCES users (id)",
        "list_id": "INTEGER REFERENCES lists (id)",
        "due_time": "TEXT",
        "repeat": "TEXT",
        "remind_before": "INTEGER",
        "priority": "INTEGER NOT NULL DEFAULT 0",
        "emoji": "TEXT",
        "doing": "INTEGER NOT NULL DEFAULT 0",
    },
    "lists": {
        "color": "TEXT NOT NULL DEFAULT 'blue'",
    },
    "users": {
        "theme": "TEXT NOT NULL DEFAULT 'default'",
        "appearance": "TEXT NOT NULL DEFAULT 'system'",
        "display_name": "TEXT",
        "avatar": "TEXT",
    },
}


def add_missing_columns(db):
    """Upgrade a database made by an older version of the app.

    CREATE TABLE IF NOT EXISTS skips a table that is already there, so an
    old table never gets new columns. Add them by hand. Old rows get the
    column's default, or NULL: for tasks.user_id that means no account
    sees those tasks.
    """
    for table, new_columns in NEW_COLUMNS.items():
        columns = [row["name"] for row in db.execute(f"PRAGMA table_info({table})")]
        for name, sql_type in new_columns.items():
            if name not in columns:
                # Table and column names can't be ? placeholders. These come
                # from the dict above, never from a user, so pasting them in is safe.
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
    db.commit()


@click.command("init-db")
@click.option("--reset", is_flag=True, help="Delete every task and account and start empty.")
def init_db_command(reset):
    """Create the database (flask --app todo init-db [--reset])."""
    if reset:
        click.confirm("Delete ALL tasks and accounts?", abort=True)
        for table in ["undo", "subtasks", "task_tags", "tags", "tasks", "lists", "users"]:
            get_db().execute(f"DROP TABLE IF EXISTS {table}")
    init_db()
    click.echo("Database ready.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    # Create the table on startup, so the app works on its first run.
    with app.app_context():
        init_db()
