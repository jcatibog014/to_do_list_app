"""Tests for the look: cards or list layout, list colors, tag colors and the banner."""
import re
import sqlite3

from conftest import TODAY
from todo import create_app
from todo.db import get_db
from todo.tasks import tag_color
from todo.validation import LIST_COLORS


def lists_in_db(app):
    with app.app_context():
        return [dict(row) for row in get_db().execute("SELECT name, color FROM lists ORDER BY id")]


# ---------- Cards or list ----------

def test_cards_are_the_default(client, add):
    add("Something")
    html = client.get("/").get_data(as_text=True)
    assert 'class="task-list view-cards"' in html
    assert 'value="cards" class="active" aria-pressed="true"' in html


def test_switch_to_list_and_back(client, post, add):
    add("Something")
    response = post("/view?status=today&q=some", {"view": "list"})
    assert response.headers["Location"] == "/?status=today&q=some"  # the view you had is kept
    assert 'class="task-list view-list"' in client.get("/").get_data(as_text=True)

    post("/view", {"view": "cards"})
    assert 'class="task-list view-cards"' in client.get("/").get_data(as_text=True)


def test_unknown_view_is_ignored(client, post, add):
    add("Something")
    post("/view", {"view": "spreadsheet"})
    assert 'class="task-list view-cards"' in client.get("/").get_data(as_text=True)


# ---------- List colors ----------

def test_new_list_with_a_chosen_color(post, app):
    post("/lists/new", {"name": "Home", "color": "teal"})
    assert lists_in_db(app) == [{"name": "Home", "color": "teal"}]


def test_new_lists_without_a_color_take_turns(post, app):
    for name in ["One", "Two", "Three"]:
        post("/lists/new", {"name": name})
    assert [l["color"] for l in lists_in_db(app)] == LIST_COLORS[:3]


def test_new_list_form_preselects_the_next_color(client, post):
    post("/lists/new", {"name": "One"})
    html = client.get("/lists").get_data(as_text=True)
    # \s+ allows any spaces or line breaks between the two attributes.
    assert re.search(rf'value="{LIST_COLORS[1]}"\s+checked', html)


def test_new_list_with_an_unknown_color_is_refused(client, post, app):
    post("/lists/new", {"name": "Home", "color": "plaid"})
    assert lists_in_db(app) == []
    assert "Pick one of the colors." in client.get("/").get_data(as_text=True)


def test_change_a_lists_color(client, post, app):
    post("/lists/new", {"name": "Home", "color": "blue"})
    response = post("/lists/1/color?list=1", {"color": "pink"})
    assert response.headers["Location"] == "/?list=1"
    assert lists_in_db(app)[0]["color"] == "pink"
    html = client.get("/?list=1").get_data(as_text=True)
    assert "“Home” is pink now." in html
    assert '<header class="hero color-pink">' in html


def test_change_color_refuses_unknown_colors(client, post, app):
    post("/lists/new", {"name": "Home", "color": "blue"})
    post("/lists/1/color", {"color": "plaid"})
    assert lists_in_db(app)[0]["color"] == "blue"


def test_cannot_recolor_someone_elses_list(post, app, other_user):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO lists (user_id, name) VALUES (?, 'Secret')", (other_user,))
        db.commit()
    assert post("/lists/1/color", {"color": "red"}).status_code == 404


def test_cards_take_their_lists_color(client, post, add):
    post("/lists/new", {"name": "Home", "color": "green"})
    add("In a list", list_id=1)
    add("In the inbox")
    html = client.get("/").get_data(as_text=True)
    assert '<li class="task color-green">' in html
    assert '<li class="task color-slate">' in html


def test_late_cards_are_marked(client, add):
    add("Late", due_date="2026-10-01")
    assert '<li class="task color-slate is-overdue">' in client.get("/").get_data(as_text=True)


# ---------- Tag colors ----------

def test_tag_colors_are_from_the_palette_and_never_change():
    assert tag_color("home") in LIST_COLORS
    assert tag_color("home") == tag_color("home")
    # Different names can get different colors.
    assert len({tag_color(name) for name in ["home", "work", "bills", "gym", "school"]}) > 1


def test_tag_chips_are_colored(client, post):
    post("/tasks/quick", {"text": "paint #home"})
    html = client.get("/").get_data(as_text=True)
    assert f'class="badge tag color-{tag_color("home")}"' in html


# ---------- The banner ----------

def test_banner_greets_and_shows_todays_progress(client, add):
    add("Today one", due_date="2026-10-19")
    add("Today two", due_date="2026-10-19", completed=True)
    add("Late", due_date="2026-10-01")
    add("Done", completed=True)
    html = " ".join(client.get("/").get_data(as_text=True).split())  # squash the template's line breaks
    assert "Monday, October 19" in html
    assert "<span data-hello>Hello</span>, alice!" in html
    assert "You have 2 tasks today (1 overdue)." in html  # Today counts late tasks too
    # The bar counts tasks due today: 1 of the 2 is done.
    assert "1 of 2 done today" in html
    assert 'aria-valuemax="2" aria-valuenow="1"' in html
    assert 'style="width: 50%"' in html


def test_banner_when_nothing_is_due(client):
    assert "Nothing due today" in client.get("/").get_data(as_text=True)


# ---------- Upgrading an old database ----------

def test_old_lists_table_gets_a_color(tmp_path):
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE lists (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,"
               " name TEXT NOT NULL, UNIQUE (user_id, name))")
    db.execute("INSERT INTO lists (user_id, name) VALUES (1, 'Work')")
    db.commit()
    db.close()

    app = create_app({"TESTING": True, "DATABASE": str(path), "TODAY": lambda: TODAY})

    assert lists_in_db(app) == [{"name": "Work", "color": "blue"}]


# ---------- Name and logo ----------

def test_app_name_and_logo(client, guest):
    html = guest.get("/login").get_data(as_text=True)
    assert "<title>Log In · Later Gator</title>" in html
    assert re.search(r'rel="icon" type="image/png" href="/static/logo\.png\?v=\d+"', html)
    assert re.search(r'class="brand-logo" src="/static/logo\.png\?v=\d+"', html)
    assert '<p class="auth-name">Later Gator</p>' in html
    assert guest.get("/static/logo.png").status_code == 200


# ---------- Gator theme, centered login, fresh static files ----------

def test_static_links_carry_a_version(guest):
    html = guest.get("/login").get_data(as_text=True)
    # The number changes whenever the file does, so browsers fetch the new one.
    assert re.search(r'href="/static/style\.css\?v=\d+"', html)
    assert re.search(r'src="/static/logo\.png\?v=\d+"', html)


def test_login_and_sign_up_use_the_centered_layout(guest):
    for url in ["/login", "/register"]:
        html = guest.get(url).get_data(as_text=True)
        assert '<div class="auth">' in html
        assert '<div class="auth-brand">' in html


def test_gator_is_the_default_theme_and_grape_is_still_there(client, post):
    html = client.get("/profile").get_data(as_text=True)
    assert '<span class="theme-name">Gator</span>' in html
    assert '<span class="theme-name">Grape</span>' in html
    post("/profile/theme", {"theme": "grape", "appearance": "light"})
    assert 'data-theme="grape"' in client.get("/").get_data(as_text=True)


def test_login_heading_is_inside_the_card(guest):
    for url, heading in [("/login", "Log In"), ("/register", "Create an Account")]:
        html = guest.get(url).get_data(as_text=True)
        card = html[html.index('<form class="card"'):html.index("</form>")]
        assert f'<h1 class="card-title">{heading}</h1>' in card
        assert "alligator.”</p>" in html  # the tagline ends without an emoji
        assert "🐊" not in html


def test_login_error_shows_inside_the_card(guest, post):
    html = post("/login", {"username": "nobody", "password": "nope nope"}).get_data(as_text=True)
    card = html[html.index('<form class="card"'):html.index("</form>")]
    assert "Incorrect username or password." in card
