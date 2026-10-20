"""Tests for the demo account made with "flask --app todo create-demo"."""
from werkzeug.security import check_password_hash

from conftest import CSRF
from todo.db import get_db
from todo.demo import DEMO_DONE, DEMO_LISTS, DEMO_TASKS


def rows(app, sql, params=()):
    with app.app_context():
        return [dict(row) for row in get_db().execute(sql, params)]


def create_demo(app, username="clientdemo", password="show me 2026"):
    """Run the command the way you would on the server."""
    return app.test_cli_runner().invoke(args=["create-demo", "--username", username, "--password", password])


def demo_user(app, username="clientdemo"):
    found = rows(app, "SELECT * FROM users WHERE username = ?", (username,))
    return found[0] if found else None


def log_in_as_demo(guest, post):
    response = post("/login", {"username": "clientdemo", "password": "show me 2026"})
    # Logging in starts a fresh session, which drops the CSRF token. A real
    # browser gets a new one with the next page; the test puts it back.
    with guest.session_transaction() as session:
        session["csrf_token"] = CSRF
    return response


# ---------- The command ----------

def test_create_demo_makes_an_account_full_of_examples(app):
    result = create_demo(app)
    assert result.exit_code == 0
    assert "Demo account ready" in result.output

    user = demo_user(app)
    assert user["is_demo"] == 1
    assert (user["display_name"], user["avatar"]) == ("Demo", "🦊")
    assert check_password_hash(user["password_hash"], "show me 2026")  # only a hash is saved

    assert len(rows(app, "SELECT * FROM lists WHERE user_id = ?", (user["id"],))) == len(DEMO_LISTS)
    tasks = rows(app, "SELECT * FROM tasks WHERE user_id = ?", (user["id"],))
    assert len(tasks) == len(DEMO_TASKS) + len(DEMO_DONE)


def test_demo_dates_count_from_today(app):
    create_demo(app)
    user_id = demo_user(app)["id"]
    due = {t["title"]: t["due_date"] for t in rows(app, "SELECT title, due_date FROM tasks WHERE user_id = ?", (user_id,))}
    assert due["Renew library card"] == "2026-10-17"   # 2 days late
    assert due["Finish thesis chapter 2"] == "2026-10-20"
    assert due["Gym"] == "2026-10-19"                 # "every Monday", and today is a Monday


def test_running_it_again_refills_the_examples_and_changes_the_password(app):
    create_demo(app)
    user_id = demo_user(app)["id"]
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))  # the client deleted everything
        db.commit()

    create_demo(app, password="a new one 99")

    user = demo_user(app)
    assert user["id"] == user_id  # the same account, not a second one
    assert check_password_hash(user["password_hash"], "a new one 99")
    assert len(rows(app, "SELECT * FROM tasks WHERE user_id = ?", (user_id,))) == len(DEMO_TASKS) + len(DEMO_DONE)
    assert len(rows(app, "SELECT * FROM lists WHERE user_id = ?", (user_id,))) == len(DEMO_LISTS)


def test_create_demo_never_touches_a_real_account(app):
    result = create_demo(app, username="alice")
    assert result.exit_code != 0
    assert "real person's account" in result.output
    assert demo_user(app, "alice")["is_demo"] == 0


def test_create_demo_checks_the_username_and_password(app):
    assert "Password must be at least 8 characters" in create_demo(app, password="short").output
    assert "letters, numbers or underscores" in create_demo(app, username="a b").output
    assert demo_user(app, "a b") is None


# ---------- Using the demo account ----------

def test_log_in_to_the_demo_and_see_the_examples(client, guest, post, app):
    create_demo(app)
    assert log_in_as_demo(guest, post).headers["Location"] == "/"
    html = client.get("/").get_data(as_text=True)
    assert "Finish thesis chapter 2" in html
    stats = " ".join(client.get("/stats").get_data(as_text=True).split())
    assert "🔥 5</p>" in stats  # done today and each of the 4 days before


def test_demo_password_and_username_stay_put(client, guest, post, app):
    create_demo(app)
    log_in_as_demo(guest, post)
    before = demo_user(app)

    html = client.get("/profile").get_data(as_text=True)
    assert "This is a demo account, so its password can" in html
    assert 'action="/profile/password"' not in html
    assert "readonly" in html

    post("/profile/password", {"current_password": "show me 2026", "new_password": "whatever1",
                               "confirm_password": "whatever1"})
    response = post("/profile", {"username": "renamed", "display_name": "Client", "avatar": ""})
    assert response.status_code == 400
    assert "The demo account&#39;s username can&#39;t be changed." in response.get_data(as_text=True)

    after = demo_user(app)
    assert (after["username"], after["password_hash"]) == (before["username"], before["password_hash"])


def test_demo_can_still_change_its_name_and_picture(guest, post, app):
    create_demo(app)
    log_in_as_demo(guest, post)
    post("/profile", {"username": "clientdemo", "display_name": "Client", "avatar": "🐼"})
    user = demo_user(app)
    assert (user["display_name"], user["avatar"]) == ("Client", "🐼")


# ---------- No public demo button ----------

def test_there_is_no_public_demo_button(guest):
    html = guest.get("/login").get_data(as_text=True)
    assert "Try the Demo" not in html
    assert guest.post("/demo", data={"csrf_token": CSRF}).status_code == 404


def test_ordinary_accounts_are_unchanged(client):
    html = client.get("/profile").get_data(as_text=True)
    assert 'action="/profile/password"' in html
    assert "readonly" not in html
