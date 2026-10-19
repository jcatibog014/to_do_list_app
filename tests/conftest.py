"""Shared test setup (pytest finds fixtures in this file automatically)."""
from datetime import date

import pytest

from todo import create_app
from todo.db import get_db

# Every test pretends today is this day, so date checks never depend on
# when the tests run.
TODAY = date(2026, 10, 19)
CSRF = "test-token"


@pytest.fixture
def app(tmp_path):
    # tmp_path is a fresh, empty folder for each test, so each test gets
    # its own empty database.
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "DATABASE": str(tmp_path / "test.sqlite"),
        "TODAY": lambda: TODAY,
    })


@pytest.fixture
def client(app):
    client = app.test_client()
    # Put a known CSRF token in the session, so post() can send it.
    with client.session_transaction() as session:
        session["csrf_token"] = CSRF
    return client


@pytest.fixture
def post(client):
    """client.post() that also sends the CSRF token, like a real form does."""
    def _post(url, data=None, **kwargs):
        return client.post(url, data={"csrf_token": CSRF, **(data or {})}, **kwargs)
    return _post


@pytest.fixture
def add(app):
    """Insert a task straight into the database and return its id.

    This skips validation, so tests can create tasks that are already
    overdue or completed.
    """
    def _add(title, due_date=None, completed=False, description=""):
        with app.app_context():
            db = get_db()
            cursor = db.execute(
                "INSERT INTO tasks (title, description, due_date, completed) VALUES (?, ?, ?, ?)",
                (title, description, due_date, int(completed)),
            )
            db.commit()
            return cursor.lastrowid
    return _add


@pytest.fixture
def fetch(app):
    """Read one task from the database (None if it doesn't exist)."""
    def _fetch(task_id):
        with app.app_context():
            row = get_db().execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(row) if row else None
    return _fetch
