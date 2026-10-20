"""Tests for Try the Demo: private demo accounts with example data."""
from conftest import CSRF
from todo.db import get_db
from todo.demo import DEMO_DONE, DEMO_LISTS, DEMO_TASKS


def rows(app, sql, params=()):
    with app.app_context():
        return [dict(row) for row in get_db().execute(sql, params)]


def logged_in_user_id(client):
    with client.session_transaction() as session:
        return session.get("user_id")


def start_demo(guest, post):
    response = post("/demo")
    user_id = logged_in_user_id(guest)
    # Logging in starts a fresh session, which drops the CSRF token. A real
    # browser gets a new one with the next page; the test puts it back.
    with guest.session_transaction() as session:
        session["csrf_token"] = CSRF
    return response, user_id


def test_login_page_has_the_demo_button(guest):
    html = guest.get("/login").get_data(as_text=True)
    assert 'action="/demo"' in html
    assert ">Try the Demo</button>" in html


def test_demo_makes_an_account_full_of_examples_and_logs_in(guest, post, app):
    response, user_id = start_demo(guest, post)
    assert response.headers["Location"] == "/"
    user = rows(app, "SELECT * FROM users WHERE id = ?", (user_id,))[0]
    assert user["is_demo"] == 1
    assert user["username"].startswith("demo_")
    assert (user["display_name"], user["avatar"]) == ("Demo", "🦊")

    assert len(rows(app, "SELECT * FROM lists WHERE user_id = ?", (user_id,))) == len(DEMO_LISTS)
    tasks = rows(app, "SELECT * FROM tasks WHERE user_id = ?", (user_id,))
    assert len(tasks) == len(DEMO_TASKS) + len(DEMO_DONE)
    assert len(rows(app, "SELECT * FROM subtasks JOIN tasks ON tasks.id = subtasks.task_id"
                         " WHERE tasks.user_id = ?", (user_id,))) == 5


def test_demo_dates_count_from_today(guest, post, app):
    _, user_id = start_demo(guest, post)
    due = {t["title"]: t["due_date"] for t in rows(app, "SELECT title, due_date FROM tasks WHERE user_id = ?", (user_id,))}
    assert due["Renew library card"] == "2026-10-17"   # 2 days late
    assert due["Finish thesis chapter 2"] == "2026-10-20"
    assert due["Gym"] == "2026-10-19"                 # "every Monday", and today is a Monday


def test_demo_pages_show_the_examples(client, guest, post):
    start_demo(guest, post)
    html = client.get("/").get_data(as_text=True)
    assert "Welcome to the demo!" in html
    assert "You're trying the demo." in html
    assert "Finish thesis chapter 2" in html
    stats = " ".join(client.get("/stats").get_data(as_text=True).split())
    assert "🔥 5</p>" in stats  # done today and each of the 4 days before


def test_every_visitor_gets_their_own_demo(guest, post, app):
    _, first = start_demo(guest, post)
    _, second = start_demo(guest, post)
    assert first != second
    assert len(rows(app, "SELECT * FROM users WHERE is_demo = 1")) == 2


def test_old_demos_are_deleted_with_everything_in_them(guest, post, app):
    _, old = start_demo(guest, post)
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET created_at = datetime('now', 'localtime', '-2 days') WHERE id = ?", (old,))
        # An ordinary account just as old must stay.
        db.execute("UPDATE users SET created_at = datetime('now', 'localtime', '-2 days') WHERE id = 1")
        db.commit()

    start_demo(guest, post)

    assert rows(app, "SELECT * FROM users WHERE id = ?", (old,)) == []
    for table in ["tasks", "lists", "tags"]:
        assert rows(app, f"SELECT * FROM {table} WHERE user_id = ?", (old,)) == []
    assert rows(app, "SELECT * FROM subtasks WHERE task_id NOT IN (SELECT id FROM tasks)") == []
    assert rows(app, "SELECT * FROM task_tags WHERE task_id NOT IN (SELECT id FROM tasks)") == []
    assert len(rows(app, "SELECT * FROM users WHERE id = 1")) == 1  # alice is still here


def test_a_deleted_demo_is_simply_logged_out(client, guest, post, app):
    _, user_id = start_demo(guest, post)
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()
    assert client.get("/").headers["Location"] == "/login"


def test_demo_accounts_have_no_password_form(client, guest, post, app):
    _, user_id = start_demo(guest, post)
    html = client.get("/profile").get_data(as_text=True)
    assert "Demo accounts don't have a password" in html
    assert 'action="/profile/password"' not in html

    before = rows(app, "SELECT password_hash FROM users WHERE id = ?", (user_id,))[0]
    response = post("/profile/password", {"current_password": "x", "new_password": "whatever1",
                                          "confirm_password": "whatever1"})
    assert response.headers["Location"] == "/profile"
    assert rows(app, "SELECT password_hash FROM users WHERE id = ?", (user_id,))[0] == before


def test_ordinary_accounts_still_change_passwords(client):
    html = client.get("/profile").get_data(as_text=True)
    assert 'action="/profile/password"' in html
    assert "You're trying the demo." not in html


def test_demo_needs_the_csrf_token(guest, app):
    assert guest.post("/demo").status_code == 400
    assert rows(app, "SELECT * FROM users WHERE is_demo = 1") == []
