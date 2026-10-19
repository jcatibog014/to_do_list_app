"""Shared test setup (pytest finds fixtures in this file automatically)."""
from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from todo import create_app
from todo.db import get_db

# Every test pretends today is this day, so date checks never depend on
# when the tests run.
TODAY = date(2026, 10, 19)
CSRF = "test-token"

# Every test starts with this account, logged in. Hashing is slow on
# purpose, so the hash is made once here instead of in every test.
USERNAME = "alice"
PASSWORD = "correct horse"
PASSWORD_HASH = generate_password_hash(PASSWORD)


@pytest.fixture
def app(tmp_path):
    # tmp_path is a fresh, empty folder for each test, so each test gets
    # its own empty database.
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "DATABASE": str(tmp_path / "test.sqlite"),
        "TODAY": lambda: TODAY,
    })
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)", (USERNAME, PASSWORD_HASH)
        )
        db.commit()
    return app


@pytest.fixture
def client(app):
    client = app.test_client()
    # Put a known CSRF token in the session, so post() can send it, and log
    # in as alice (user 1) the same way auth.log_in() does.
    with client.session_transaction() as session:
        session["csrf_token"] = CSRF
        session["user_id"] = 1
    return client


@pytest.fixture
def guest(client):
    """The same test client, logged out."""
    with client.session_transaction() as session:
        del session["user_id"]
    return client


@pytest.fixture
def other_user(app):
    """Create a second account, bob, and return its id."""
    with app.app_context():
        db = get_db()
        cursor = db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)", ("bob", PASSWORD_HASH)
        )
        db.commit()
        return cursor.lastrowid


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
    overdue or completed. Tasks belong to alice (user 1) unless user_id says
    otherwise.
    """
    def _add(title, due_date=None, completed=False, description="", user_id=1):
        with app.app_context():
            db = get_db()
            cursor = db.execute(
                "INSERT INTO tasks (user_id, title, description, due_date, completed)"
                " VALUES (?, ?, ?, ?, ?)",
                (user_id, title, description, due_date, int(completed)),
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
