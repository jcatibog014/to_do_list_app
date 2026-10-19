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


@click.command("init-db")
@click.option("--reset", is_flag=True, help="Delete every task and start with an empty table.")
def init_db_command(reset):
    """Create the database (flask --app todo init-db [--reset])."""
    if reset:
        click.confirm("Delete ALL tasks?", abort=True)
        get_db().execute("DROP TABLE IF EXISTS tasks")
    init_db()
    click.echo("Database ready.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    # Create the table on startup, so the app works on its first run.
    with app.app_context():
        init_db()
