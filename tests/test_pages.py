"""Tests for the Lists, Calendar and Stats pages."""
import re
import sqlite3
from datetime import date

import pytest

from conftest import TODAY
from todo import create_app
from todo.db import get_db
from todo.pages import streaks


def set_completed_at(app, task_id, when):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE tasks SET completed = 1, completed_at = ? WHERE id = ?", (when, task_id))
        db.commit()


# ---------- Navigation ----------

@pytest.mark.parametrize("url, label", [
    ("/", "Today"), ("/lists", "Lists"), ("/calendar", "Calendar"), ("/profile", "Profile"),
    ("/stats", "Profile"),  # Stats lives under Profile
])
def test_bottom_nav_marks_the_current_page(client, url, label):
    html = client.get(url).get_data(as_text=True)
    # The lit tab in the bottom bar: its icon, then its label.
    lit = re.search(r'<a class="active"[^>]*aria-current="page">\s*<span class="nav-icon"[^>]*>[^<]*</span>(\w+)', html)
    assert lit and lit.group(1) == label
    assert 'class="fab"' in html  # the floating + button is on every page


@pytest.mark.parametrize("url", ["/lists", "/calendar", "/stats", "/focus", "/profile"])
def test_new_pages_need_login(guest, url):
    assert guest.get(url).headers["Location"] == "/login"


# ---------- Lists page ----------

def test_lists_page_counts_tasks(client, post, add):
    post("/lists/new", {"name": "Work", "color": "teal"})
    add("Open one", list_id=1)
    add("Done one", list_id=1, completed=True)
    add("Inbox one")
    html = " ".join(client.get("/lists").get_data(as_text=True).split())
    assert '<article class="list-card color-teal" id="list-1">' in html
    assert "1 open · 1 done" in html


def test_rename_a_list(client, post, app):
    post("/lists/new", {"name": "Wrok"})
    response = post("/lists/1/rename", {"name": "Work", "next": "lists"})
    assert response.headers["Location"] == "/lists"
    with app.app_context():
        assert get_db().execute("SELECT name FROM lists").fetchone()["name"] == "Work"


def test_rename_refuses_a_taken_name(client, post, app):
    post("/lists/new", {"name": "Work"})
    post("/lists/new", {"name": "Home"})
    post("/lists/2/rename", {"name": "work"})
    with app.app_context():
        assert get_db().execute("SELECT name FROM lists WHERE id = 2").fetchone()["name"] == "Home"
    assert "You already have a list called “work”." in client.get("/").get_data(as_text=True)


def test_list_actions_can_return_to_the_lists_page(post):
    assert post("/lists/new", {"name": "Work", "next": "lists"}).headers["Location"] == "/lists"
    assert post("/lists/1/color", {"color": "red", "next": "lists"}).headers["Location"] == "/lists"
    assert post("/lists/1/delete", {"next": "lists"}).headers["Location"] == "/lists"


# ---------- Calendar ----------

def test_calendar_shows_the_month_with_tasks_on_their_days(client, add):
    add("Dentist", due_date="2026-10-23", emoji="🦷")
    add("Thanksgiving", due_date="2026-11-26")
    html = client.get("/calendar").get_data(as_text=True)
    assert "<h1>October 2026</h1>" in html
    assert "🦷 Dentist" in html
    assert "Thanksgiving" not in html  # November 26 isn't in October's grid
    # The grid starts on the Sunday before October 1st (Sep 27).
    assert 'day=2026-09-27' in html


def test_calendar_other_month_and_selected_day(client, add):
    add("Party", due_date="2026-12-31")
    html = client.get("/calendar?month=2026-12&day=2026-12-31").get_data(as_text=True)
    assert "<h1>December 2026</h1>" in html
    assert "Thursday, December 31" in html
    assert 'class="task-list view-list"' in html  # the day's tasks as cards
    assert "month=2026-11" in html and "month=2027-01" in html  # previous and next month


def test_calendar_selects_today_in_this_month(client, add):
    add("Today's thing", due_date="2026-10-19")
    html = client.get("/calendar").get_data(as_text=True)
    assert "Monday, October 19" in html
    assert "is-today is-selected" in html


def test_calendar_with_a_bad_month_shows_this_month(client):
    assert "<h1>October 2026</h1>" in client.get("/calendar?month=nonsense").get_data(as_text=True)


def test_calendar_actions_come_back_to_the_same_day(post, add):
    task_id = add("Party", due_date="2026-12-31")
    response = post(f"/tasks/{task_id}/toggle", {"next": "calendar", "month": "2026-12", "day": "2026-12-31"})
    assert response.headers["Location"] == "/calendar?month=2026-12&day=2026-12-31"


# ---------- Stats and streaks ----------

def days(*numbers):
    return {date(2026, 10, n) for n in numbers}


@pytest.mark.parametrize("done_days, current, best", [
    (set(), 0, 0),
    (days(19), 1, 1),
    (days(17, 18, 19), 3, 3),
    (days(16, 17, 18), 3, 3),     # nothing yet today, but yesterday counts
    (days(10, 11, 12, 13, 18), 1, 4),
    (days(15, 16), 0, 2),          # broken: nothing yesterday or today
])
def test_streaks(done_days, current, best):
    assert streaks(done_days, TODAY) == (current, best)


def test_stats_page(client, add, app):
    for n, when in enumerate(["2026-10-18 09:00:00", "2026-10-19 10:00:00", "2026-10-19 11:00:00"], start=1):
        add(f"Done {n}")
        set_completed_at(app, n, when)
    add("Open", due_date="2026-10-19")
    add("Late", due_date="2026-10-01")
    html = " ".join(client.get("/stats").get_data(as_text=True).split())
    assert "🔥 2</p> <p class=\"stat-label\">day streak · best 2" in html
    assert '<p class="stat-number">2</p><p class="stat-label">open</p>' in html
    assert '<p class="stat-number">3</p><p class="stat-label">done</p>' in html
    assert '<span class="week-count">2</span>' in html  # two done today


# ---------- Upgrading an old database ----------

def test_old_database_gets_the_new_columns(tmp_path):
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL,"
               " password_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT '')")
    db.execute("INSERT INTO users (username, password_hash) VALUES ('ana', 'x')")
    db.commit()
    db.close()

    app = create_app({"TESTING": True, "DATABASE": str(path), "TODAY": lambda: TODAY})

    with app.app_context():
        user = get_db().execute("SELECT * FROM users").fetchone()
        task_columns = {r["name"] for r in get_db().execute("PRAGMA table_info(tasks)")}
    assert (user["theme"], user["appearance"]) == ("default", "system")
    assert {"priority", "emoji", "doing"} <= task_columns
