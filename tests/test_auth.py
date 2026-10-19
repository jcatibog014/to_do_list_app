"""Tests for accounts (register, log in, log out) and for keeping each
user's tasks private."""
import sqlite3

import pytest
from werkzeug.security import check_password_hash

from todo import create_app
from todo.db import get_db

from conftest import PASSWORD, TODAY, USERNAME


def logged_in_user_id(client):
    with client.session_transaction() as session:
        return session.get("user_id")


# ---------- Logged out ----------

@pytest.mark.parametrize("url", ["/", "/tasks/new", "/tasks/1/edit"])
def test_pages_send_guests_to_login(guest, url):
    response = guest.get(url)
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_guests_cannot_change_tasks(guest, post, add, fetch):
    task_id = add("Private")
    response = post(f"/tasks/{task_id}/delete")
    assert response.headers["Location"] == "/login"
    assert fetch(task_id) is not None


def test_login_page(guest):
    response = guest.get("/login")
    assert response.status_code == 200
    assert 'name="password"' in response.get_data(as_text=True)


# ---------- Register ----------

def test_register_creates_account_and_logs_in(guest, post, app):
    response = post("/register", {"username": "new_user", "password": "secret123", "confirm": "secret123"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/"

    with app.app_context():
        user = get_db().execute("SELECT * FROM users WHERE username = 'new_user'").fetchone()
    # Only a hash is saved, and it still checks out against the password.
    assert user["password_hash"] != "secret123"
    assert check_password_hash(user["password_hash"], "secret123")

    assert logged_in_user_id(guest) == user["id"]
    assert "Welcome, new_user!" in guest.get("/").get_data(as_text=True)


@pytest.mark.parametrize("taken", [USERNAME, USERNAME.upper()])
def test_register_refuses_a_taken_username(guest, post, taken):
    response = post("/register", {"username": taken, "password": "secret123", "confirm": "secret123"})
    assert response.status_code == 400
    assert "That username is taken." in response.get_data(as_text=True)
    assert logged_in_user_id(guest) is None


def test_invalid_register_keeps_username_but_not_password(guest, post):
    response = post("/register", {"username": "new_user", "password": "short", "confirm": "short"})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "Password must be at least 8 characters." in html
    assert 'value="new_user"' in html
    assert "short" not in html


# ---------- Log in and out ----------

@pytest.mark.parametrize("username", [USERNAME, USERNAME.upper(), f"  {USERNAME} "])
def test_login(guest, post, username):
    response = post("/login", {"username": username, "password": PASSWORD})
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert logged_in_user_id(guest) == 1


@pytest.mark.parametrize("username, password", [
    (USERNAME, "wrong password"),
    ("nobody", PASSWORD),
])
def test_failed_login_gives_one_message_for_both_mistakes(guest, post, username, password):
    response = post("/login", {"username": username, "password": password})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "Incorrect username or password." in html
    assert f'value="{username}"' in html
    assert logged_in_user_id(guest) is None


def test_header_shows_who_is_logged_in(client):
    html = client.get("/").get_data(as_text=True)
    assert f'<span class="account-name">{USERNAME}</span>' in html
    assert "Log out" in html


def test_logout(client, post):
    response = post("/logout")
    assert response.headers["Location"] == "/login"
    assert logged_in_user_id(client) is None
    assert client.get("/").headers["Location"] == "/login"


def test_logout_must_be_a_post(client):
    assert client.get("/logout").status_code == 405
    assert logged_in_user_id(client) == 1


# ---------- Privacy: each user sees only their own tasks ----------

def test_list_shows_only_my_tasks(client, add, other_user):
    add("Mine")
    add("Bob's secret", user_id=other_user)
    html = client.get("/").get_data(as_text=True)
    assert "Mine" in html
    assert "Bob&#39;s secret" not in html
    assert 'All <span class="count">1</span>' in html


def test_new_tasks_belong_to_me(post, fetch):
    post("/tasks/new", {"title": "Buy milk"})
    assert fetch(1)["user_id"] == 1


@pytest.mark.parametrize("method, action", [
    ("get", "edit"),
    ("post", "edit"),
    ("post", "toggle"),
    ("post", "delete"),
])
def test_someone_elses_task_is_not_found(client, post, add, fetch, other_user, method, action):
    task_id = add("Bob's secret", user_id=other_user)
    url = f"/tasks/{task_id}/{action}"
    response = client.get(url) if method == "get" else post(url, {"title": "hacked"})
    assert response.status_code == 404
    task = fetch(task_id)
    assert task["title"] == "Bob's secret"
    assert task["completed"] == 0


# ---------- Upgrading an old database ----------

def test_old_database_gets_user_id_column(tmp_path):
    # Build a tasks table the way it looked before accounts existed.
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL,"
               " description TEXT NOT NULL DEFAULT '', due_date TEXT,"
               " completed INTEGER NOT NULL DEFAULT 0,"
               " created_at TEXT NOT NULL DEFAULT '', completed_at TEXT)")
    db.execute("INSERT INTO tasks (title) VALUES ('Old task')")
    db.commit()
    db.close()

    app = create_app({"TESTING": True, "DATABASE": str(path), "TODAY": lambda: TODAY})

    with app.app_context():
        task = get_db().execute("SELECT * FROM tasks").fetchone()
    assert task["title"] == "Old task"
    assert task["user_id"] is None  # nobody's, so no account sees it
