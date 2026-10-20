"""Tests for the planning features: quick add, the Today view, lists, tags,
repeating tasks and reminders."""
import sqlite3

import pytest

from conftest import TODAY
from todo import create_app
from todo.db import get_db


@pytest.fixture
def make_list(app):
    """Create a list for alice (or another user) and return its id."""
    def _make_list(name, user_id=1):
        with app.app_context():
            db = get_db()
            cursor = db.execute("INSERT INTO lists (user_id, name) VALUES (?, ?)", (user_id, name))
            db.commit()
            return cursor.lastrowid
    return _make_list


# ---------- Quick add ----------

def test_quick_add_saves_every_part(client, post, fetch, tags_of):
    response = post("/tasks/quick", {"text": "pay rent friday 5pm #home #bills"})
    assert response.status_code == 302

    task = fetch(1)
    assert task["title"] == "Pay rent"
    assert (task["due_date"], task["due_time"]) == ("2026-10-23", "17:00")
    assert task["remind_before"] == 0  # a typed time also sets a reminder
    assert task["list_id"] is None
    assert tags_of(1) == ["bills", "home"]

    html = client.get("/").get_data(as_text=True)
    assert "Added “Pay rent”. Due Oct 23, 5:00 PM." in html


def test_quick_add_without_a_time_sets_no_reminder(post, fetch):
    post("/tasks/quick", {"text": "buy milk tomorrow"})
    task = fetch(1)
    assert task["due_date"] == "2026-10-20"
    assert task["remind_before"] is None


def test_quick_add_repeat_starts_on_the_first_matching_day(post, fetch):
    post("/tasks/quick", {"text": "team meeting every 2nd monday 10am"})
    task = fetch(1)
    assert task["repeat"] == "nth:2:0"
    assert task["due_date"] == "2026-11-09"


def test_quick_add_goes_into_the_list_on_screen(post, fetch, make_list):
    work = make_list("Work")
    response = post(f"/tasks/quick?list={work}", {"text": "send report"})
    assert response.headers["Location"] == f"/?list={work}"
    assert fetch(1)["list_id"] == work


@pytest.mark.parametrize("text, message", [
    ("", "Type what the task is"),
    ("tomorrow 5pm", "Type what the task is"),
    ("party feb 30", "That date doesn&#39;t exist."),
    ("party 2026-10-01", "Due date can&#39;t be in the past."),
])
def test_quick_add_errors_keep_the_text(post, fetch, text, message):
    response = post("/tasks/quick", {"text": text})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert message in html
    assert f'value="{text}"' in html
    assert fetch(1) is None


def test_quick_add_cannot_use_someone_elses_list(post, fetch, make_list, other_user):
    bobs = make_list("Bob's", user_id=other_user)
    response = post(f"/tasks/quick?list={bobs}", {"text": "sneaky"})
    assert response.status_code == 404
    assert fetch(1) is None


# ---------- Today view and times ----------

def test_today_shows_late_and_due_today_in_time_order(client, add):
    add("Late one", due_date="2026-10-10")
    add("Afternoon", due_date="2026-10-19", due_time="15:00")
    add("Morning", due_date="2026-10-19", due_time="08:30")
    add("Any time today", due_date="2026-10-19")
    add("Task-for-the-20th", due_date="2026-10-20")
    add("Done today", due_date="2026-10-19", completed=True)

    html = client.get("/?status=today").get_data(as_text=True)
    order = ["Late one", "Morning", "Afternoon", "Any time today"]
    assert [html.index(t) for t in order] == sorted(html.index(t) for t in order)
    assert "Task-for-the-20th" not in html
    assert "Done today" not in html
    assert "Due today, 8:30 AM" in html
    assert 'Today <span class="count">4</span>' in html


def test_empty_today_view(client, add):
    add("Someday")
    assert "Nothing due today." in client.get("/?status=today").get_data(as_text=True)


# ---------- Lists ----------

def test_create_list_and_open_it(client, post, app):
    response = post("/lists/new", {"name": "  Work  "})
    assert response.status_code == 302
    assert response.headers["Location"] == "/?list=1"
    html = client.get("/?list=1").get_data(as_text=True)
    assert "<h1>Work</h1>" in html
    assert "Made the list “Work”." in html


def test_list_names_are_unique_per_user(client, post, make_list, other_user):
    make_list("Work", user_id=other_user)  # bob's "Work" doesn't count
    make_list("Work")
    response = post("/lists/new", {"name": "WORK"})
    assert response.headers["Location"] == "/"
    html = client.get("/").get_data(as_text=True)
    assert "You already have a list called “WORK”." in html
    assert "flash-error" in html


def test_blank_list_name_is_refused(client, post):
    post("/lists/new", {"name": "  "})
    assert "Give the list a name." in client.get("/").get_data(as_text=True)


def test_list_and_inbox_views(client, add, make_list):
    work = make_list("Work")
    add("Work task", list_id=work)
    add("Loose task")

    html = client.get(f"/?list={work}").get_data(as_text=True)
    assert "Work task" in html and "Loose task" not in html

    html = client.get("/?list=inbox").get_data(as_text=True)
    assert "Loose task" in html and "Work task" not in html

    # "All lists" shows both, with the list's name on the task.
    html = client.get("/").get_data(as_text=True)
    assert "Work task" in html and "Loose task" in html
    assert 'class="badge badge-list"' in html


def test_delete_list_moves_its_tasks_to_the_inbox(client, post, add, fetch, make_list):
    work = make_list("Work")
    task_id = add("Work task", list_id=work)
    response = post(f"/lists/{work}/delete")
    assert response.headers["Location"] == "/"
    assert fetch(task_id)["list_id"] is None
    assert client.get(f"/?list={work}").status_code == 404


def test_someone_elses_list_is_not_found(client, post, make_list, other_user):
    bobs = make_list("Secret", user_id=other_user)
    assert client.get(f"/?list={bobs}").status_code == 404
    assert post(f"/lists/{bobs}/delete").status_code == 404


def test_task_form_refuses_someone_elses_list(post, fetch, make_list, other_user):
    bobs = make_list("Secret", user_id=other_user)
    response = post("/tasks/new", {"title": "x", "list_id": str(bobs)})
    assert response.status_code == 400
    assert "Choose a list from the menu." in response.get_data(as_text=True)
    assert fetch(1) is None


def test_new_task_form_starts_in_the_list_on_screen(client, make_list):
    work = make_list("Work")
    html = client.get(f"/tasks/new?list={work}").get_data(as_text=True)
    assert f'<option value="{work}" selected>Work</option>' in html


# ---------- Tags ----------

def test_form_saves_and_replaces_tags(post, add, tags_of):
    post("/tasks/new", {"title": "Paint", "tags": "home, #DIY"})
    assert tags_of(1) == ["diy", "home"]

    post("/tasks/1/edit", {"title": "Paint", "tags": "garden"})
    assert tags_of(1) == ["garden"]


def test_tag_filter_and_search(client, post):
    post("/tasks/quick", {"text": "paint fence #home"})
    post("/tasks/quick", {"text": "send report #work"})
    client.get("/")  # shows (and so clears) the "Added …" messages

    html = client.get("/?tag=home").get_data(as_text=True)
    assert "Paint fence" in html and "Send report" not in html
    assert "Showing tasks tagged <strong>#home</strong>" in html

    html = client.get("/?q=%23work").get_data(as_text=True)  # %23 is "#"
    assert "Send report" in html and "Paint fence" not in html


def test_tags_are_private(client, post, add, other_user, app):
    bobs = add("Bob's task", user_id=other_user)
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO tags (user_id, name) VALUES (?, 'home')", (other_user,))
        db.execute("INSERT INTO task_tags (task_id, tag_id) VALUES (?, 1)", (bobs,))
        db.commit()
    post("/tasks/quick", {"text": "mine #home"})
    html = client.get("/?tag=home").get_data(as_text=True)
    assert "Mine" in html and "Bob" not in html


def test_deleting_a_task_removes_its_tag_links(post, app):
    post("/tasks/quick", {"text": "temp #home"})
    post("/tasks/1/delete")
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM task_tags").fetchone()[0] == 0


# ---------- Edit form ----------

def test_edit_form_shows_the_new_fields(client, post):
    post("/tasks/quick", {"text": "standup every weekday 9:15am #work"})
    html = client.get("/tasks/1/edit").get_data(as_text=True)
    assert 'value="09:15"' in html
    assert 'value="every weekday"' in html
    assert 'value="work"' in html
    assert '<option value="0" selected>At the due time</option>' in html


# ---------- Repeating tasks ----------

def test_completing_a_repeating_task_makes_the_next_one(client, post, add, fetch, tags_of, app):
    post("/tasks/quick", {"text": "water plants every 3 days 8am #home"})
    first = fetch(1)
    assert first["due_date"] == "2026-10-19"

    post("/tasks/1/toggle")
    done, nxt = fetch(1), fetch(2)
    assert done["completed"] == 1
    assert done["repeat"] is None  # the copy has the rule now
    assert nxt["completed"] == 0
    assert (nxt["title"], nxt["due_date"], nxt["due_time"]) == ("Water plants", "2026-10-22", "08:00")
    assert (nxt["repeat"], nxt["remind_before"]) == ("day:3", 0)
    assert tags_of(2) == ["home"]
    assert "Next one: Due Oct 22, 8:00 AM." in client.get("/").get_data(as_text=True)


def test_untick_and_retick_makes_no_extra_copy(post, add, fetch):
    task_id = add("Weekly review", due_date="2026-10-19", repeat="week:1")
    post(f"/tasks/{task_id}/toggle")  # done: makes task 2
    post(f"/tasks/{task_id}/toggle")  # not done
    post(f"/tasks/{task_id}/toggle")  # done again: no repeat left, so no copy
    assert fetch(3) is None
    assert fetch(2)["due_date"] == "2026-10-26"


def test_late_repeating_task_skips_past_dates(post, add, fetch):
    task_id = add("Daily pills", due_date="2026-10-15", repeat="day:1")
    post(f"/tasks/{task_id}/toggle")
    assert fetch(2)["due_date"] == "2026-10-20"


def test_repeat_label_on_the_list(client, add):
    add("Rent", due_date="2026-10-31", repeat="month:1")
    assert "↻ Every month" in client.get("/").get_data(as_text=True)


# ---------- Reminders ----------

def test_reminders_feed(client, add, other_user):
    add("Dentist", due_date="2026-10-20", due_time="15:30", remind_before=60)
    add("At noon", due_date="2026-10-19", due_time="12:00", remind_before=0)
    add("No reminder", due_date="2026-10-19", due_time="12:00")
    add("Already done", due_date="2026-10-19", due_time="12:00", remind_before=0, completed=True)
    add("Bob's", due_date="2026-10-19", due_time="12:00", remind_before=0, user_id=other_user)

    response = client.get("/reminders")
    assert response.is_json
    assert response.json == {"reminders": [
        {"id": 1, "title": "Dentist", "at": "2026-10-20T14:30", "when": "Due tomorrow, 3:30 PM"},
        {"id": 2, "title": "At noon", "at": "2026-10-19T12:00", "when": "Due today, 12:00 PM"},
    ]}


def test_reminders_need_login(guest):
    assert guest.get("/reminders").headers["Location"] == "/login"


def test_pages_load_the_reminder_script_only_when_logged_in(client, guest):
    assert "reminders.js" not in guest.get("/login").get_data(as_text=True)
    with client.session_transaction() as session:
        session["user_id"] = 1
    assert "reminders.js" in client.get("/").get_data(as_text=True)


# ---------- Upgrading an old database ----------

def test_old_database_gets_every_new_column(tmp_path):
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL,"
               " description TEXT NOT NULL DEFAULT '', due_date TEXT,"
               " completed INTEGER NOT NULL DEFAULT 0,"
               " created_at TEXT NOT NULL DEFAULT '', completed_at TEXT)")
    db.commit()
    db.close()

    app = create_app({"TESTING": True, "DATABASE": str(path), "TODAY": lambda: TODAY})

    with app.app_context():
        columns = {row["name"] for row in get_db().execute("PRAGMA table_info(tasks)")}
        tables = {row["name"] for row in get_db().execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"user_id", "list_id", "due_time", "repeat", "remind_before"} <= columns
    assert {"users", "lists", "tags", "task_tags"} <= tables
