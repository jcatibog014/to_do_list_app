"""Tests for the look: cards or list layout, list colors, tag colors and the banner."""
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
    html = client.get("/").get_data(as_text=True)
    assert f'value="{LIST_COLORS[1]}"\n                       checked' in html


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

def test_banner_shows_the_date_and_a_summary(client, add):
    add("Today one", due_date="2026-10-19")
    add("Today two", due_date="2026-10-19")
    add("Late", due_date="2026-10-01")
    add("Done", completed=True)
    html = client.get("/").get_data(as_text=True)
    assert "Monday, October 19" in html
    assert "3 to do today · 1 overdue · 1 done" in html  # Today counts late tasks too


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
