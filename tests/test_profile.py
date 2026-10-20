"""Tests for the profile page: picture, name, username, password and theme."""
from werkzeug.security import check_password_hash

from conftest import PASSWORD
from todo.db import get_db


def me(app):
    with app.app_context():
        return dict(get_db().execute("SELECT * FROM users WHERE id = 1").fetchone())


def info(**fields):
    """The "Your info" form as it's sent, with some fields changed."""
    return {"username": "alice", "display_name": "", "avatar": "", **fields}


def set_completed_at(app, task_id, when):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE tasks SET completed = 1, completed_at = ? WHERE id = ?", (when, task_id))
        db.commit()


# ---------- The page ----------

def test_profile_page(client, add):
    add("Open one")
    add("Done one", completed=True)
    html = " ".join(client.get("/profile").get_data(as_text=True).split())
    assert "<h1>alice</h1>" in html
    assert "@alice" in html
    assert '<strong>1</strong> Done' in html and '<strong>1</strong> Open' in html
    assert 'href="/stats"' in html
    # With no picture, the first letter stands in.
    assert '<span class="avatar avatar-big" aria-hidden="true">A</span>' in html


def test_top_bar_links_to_the_profile(client):
    html = client.get("/").get_data(as_text=True)
    assert '<a class="account-link" href="/profile"' in html


# ---------- Your info ----------

def test_save_picture_and_name(client, post, app):
    response = post("/profile", info(display_name="  Alice   Santos ", avatar="🦊"))
    assert response.headers["Location"] == "/profile"
    user = me(app)
    assert (user["display_name"], user["avatar"]) == ("Alice Santos", "🦊")

    html = client.get("/").get_data(as_text=True)
    assert "Saved your profile." in html
    assert "<span data-hello>Hello</span>, Alice Santos!" in html  # the greeting uses the name
    assert '<span class="avatar avatar-small" aria-hidden="true">🦊</span>' in html


def test_clearing_the_name_goes_back_to_the_username(client, post, app):
    post("/profile", info(display_name="Ali"))
    post("/profile", info(display_name="   "))
    assert me(app)["display_name"] is None
    assert "<h1>alice</h1>" in client.get("/profile").get_data(as_text=True)


def test_change_username_then_log_in_with_it(client, post):
    post("/profile", info(username="alice_s"))
    with client.session_transaction() as session:  # log out
        session.pop("user_id")
    response = post("/login", {"username": "alice_s", "password": PASSWORD})
    assert response.headers["Location"] == "/"


def test_username_taken_by_someone_else(post, app, other_user):
    response = post("/profile", info(username="BOB"))
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "That username is taken." in html
    assert 'value="BOB"' in html  # what was typed is kept
    assert me(app)["username"] == "alice"


def test_changing_only_the_capitals_of_your_own_name(post, app):
    post("/profile", info(username="Alice"))
    assert me(app)["username"] == "Alice"


def test_bad_info_is_refused(post, app):
    response = post("/profile", info(username="a b", display_name="x" * 41, avatar="<b>"))
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert 'id="username-error"' in html
    assert 'id="display_name-error"' in html
    assert 'id="avatar-error"' in html
    assert me(app)["display_name"] is None


# ---------- Password ----------

def change(post, current=PASSWORD, new="brand new pw", confirm=None):
    return post("/profile/password", {"current_password": current, "new_password": new,
                                      "confirm_password": new if confirm is None else confirm})


def test_change_password(client, post, app):
    response = change(post)
    assert response.headers["Location"] == "/profile"
    assert check_password_hash(me(app)["password_hash"], "brand new pw")
    assert "Changed your password." in client.get("/profile").get_data(as_text=True)


def test_wrong_current_password(post, app):
    response = change(post, current="not it")
    assert response.status_code == 400
    assert "That isn&#39;t your current password." in response.get_data(as_text=True)
    assert check_password_hash(me(app)["password_hash"], PASSWORD)


def test_new_passwords_must_match_and_be_long_enough(post, app):
    response = change(post, new="brand new pw", confirm="brand new pv")
    assert "The new passwords don&#39;t match." in response.get_data(as_text=True)
    response = change(post, new="short")
    assert "at least 8 characters" in response.get_data(as_text=True)
    assert check_password_hash(me(app)["password_hash"], PASSWORD)


def test_passwords_are_never_sent_back(post):
    html = change(post, current="my secret guess").get_data(as_text=True)
    assert "my secret guess" not in html
    assert "brand new pw" not in html


# ---------- Theme ----------

def test_choose_a_free_theme_and_dark_mode(client, post):
    response = post("/profile/theme", {"theme": "ocean", "appearance": "dark"})
    assert response.headers["Location"] == "/profile#theme"
    html = client.get("/").get_data(as_text=True)
    assert 'data-theme="ocean"' in html
    assert 'data-appearance="dark"' in html


def test_locked_theme_is_refused(client, post):
    post("/profile/theme", {"theme": "sunset", "appearance": "light"})
    html = client.get("/profile").get_data(as_text=True)
    assert "Sunset unlocks after a 7-day streak." in html
    assert 'data-theme="default"' in html


def test_streak_unlocks_a_theme(client, post, add, app):
    for n, day in enumerate([17, 18, 19], start=1):
        add(f"Done {n}")
        set_completed_at(app, n, f"2026-10-{day} 09:00:00")
    post("/profile/theme", {"theme": "matcha", "appearance": "system"})
    assert 'data-theme="matcha"' in client.get("/").get_data(as_text=True)


def test_stats_page_points_to_the_theme(client):
    assert 'href="/profile#theme"' in client.get("/stats").get_data(as_text=True)


def test_stats_page_uses_the_display_name(client, post):
    post("/profile", info(display_name="Ali"))
    assert "<h1>Ali</h1>" in client.get("/stats").get_data(as_text=True)
