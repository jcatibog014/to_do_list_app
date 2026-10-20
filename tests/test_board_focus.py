"""Tests for subtasks, the board, focus mode, quick actions and undo."""
import json

import pytest

from todo.db import get_db

FETCH = {"X-Requested-With": "fetch"}  # what app.js and focus.js send


def rows(app, sql, params=()):
    with app.app_context():
        return [dict(row) for row in get_db().execute(sql, params)]


def subtasks_of(app, task_id):
    return rows(app, "SELECT title, done FROM subtasks WHERE task_id = ? ORDER BY id", (task_id,))


# ---------- New fields: emoji and priority ----------

def test_form_saves_emoji_and_priority(post, fetch):
    post("/tasks/new", {"title": "Groceries", "emoji": "🛒", "priority": "1"})
    task = fetch(1)
    assert (task["emoji"], task["priority"]) == ("🛒", 1)


def test_quick_add_reads_emoji_and_priority(post, fetch):
    post("/tasks/quick", {"text": "💪 gym tomorrow 6am !"})
    task = fetch(1)
    assert (task["title"], task["emoji"], task["priority"]) == ("Gym", "💪", 1)  # the first letter is capitalized


def test_priority_cards_glow(client, add):
    add("Big one", priority=1)
    html = client.get("/").get_data(as_text=True)
    assert '<li class="task color-slate is-priority">' in html
    assert "⭐ High" in html


# ---------- Subtasks ----------

def test_new_task_form_adds_subtasks(post, app):
    post("/tasks/new", {"title": "Trip", "subtasks": "passport\n\n  charger  \n"})
    assert subtasks_of(app, 1) == [{"title": "Passport", "done": 0}, {"title": "Charger", "done": 0}]


def test_add_tick_and_remove_a_subtask(client, post, add, app):
    task_id = add("Trip")
    response = post(f"/tasks/{task_id}/subtasks", {"title": "passport", "next": "edit"})
    assert response.headers["Location"] == f"/tasks/{task_id}/edit"
    post("/subtasks/1/toggle", {"next": "edit"})
    assert subtasks_of(app, task_id) == [{"title": "Passport", "done": 1}]

    post("/subtasks/1/delete")
    assert subtasks_of(app, task_id) == []


def test_blank_subtask_is_refused(client, post, add, app):
    task_id = add("Trip")
    post(f"/tasks/{task_id}/subtasks", {"title": "  "})
    assert subtasks_of(app, task_id) == []
    assert "Type the subtask first." in client.get("/").get_data(as_text=True)


def test_card_shows_subtask_progress(client, post):
    post("/tasks/new", {"title": "Trip", "subtasks": "a\nb\nc\nd"})
    post("/subtasks/1/toggle")
    html = client.get("/").get_data(as_text=True)
    assert 'stroke-dasharray="25 100"' in html  # the ring is a quarter full
    assert "1 of 4" in html


def test_someone_elses_subtask_is_not_found(post, add, app, other_user):
    bobs = add("Bob's", user_id=other_user)
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO subtasks (task_id, title) VALUES (?, 'secret')", (bobs,))
        db.commit()
    assert post("/subtasks/1/toggle").status_code == 404
    assert post("/subtasks/1/delete").status_code == 404
    assert post(f"/tasks/{bobs}/subtasks", {"title": "x"}).status_code == 404


def test_deleting_a_task_deletes_its_subtasks(post, app):
    post("/tasks/new", {"title": "Trip", "subtasks": "a\nb"})
    post("/tasks/1/delete")
    assert rows(app, "SELECT * FROM subtasks") == []


def test_repeating_copy_gets_a_fresh_checklist(post, add, app):
    task_id = add("Weekly shop", due_date="2026-10-19", repeat="week:1")
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO subtasks (task_id, title, done) VALUES (?, 'milk', 1)", (task_id,))
        db.commit()
    post(f"/tasks/{task_id}/toggle")
    assert subtasks_of(app, 2) == [{"title": "milk", "done": 0}]


# ---------- Quick actions ----------

def test_move_to_tomorrow_keeps_the_time(post, add, fetch):
    task_id = add("Call", due_date="2026-10-19", due_time="15:00")
    post(f"/tasks/{task_id}/tomorrow")
    task = fetch(task_id)
    assert (task["due_date"], task["due_time"]) == ("2026-10-20", "15:00")


def test_toggle_priority(post, add, fetch):
    task_id = add("Thing")
    post(f"/tasks/{task_id}/priority")
    assert fetch(task_id)["priority"] == 1
    post(f"/tasks/{task_id}/priority")
    assert fetch(task_id)["priority"] == 0


def test_move_to_another_list_and_back_to_inbox(client, post, add, fetch, app):
    post("/lists/new", {"name": "Work"})
    task_id = add("Report")
    post(f"/tasks/{task_id}/move", {"list_id": "1"})
    assert fetch(task_id)["list_id"] == 1
    assert "Moved “Report” to Work." in client.get("/").get_data(as_text=True)
    post(f"/tasks/{task_id}/move", {"list_id": ""})
    assert fetch(task_id)["list_id"] is None


def test_cannot_move_into_someone_elses_list(post, add, fetch, app, other_user):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO lists (user_id, name) VALUES (?, 'Secret')", (other_user,))
        db.commit()
    task_id = add("Mine")
    assert post(f"/tasks/{task_id}/move", {"list_id": "1"}).status_code == 400
    assert fetch(task_id)["list_id"] is None


def test_every_card_has_a_menu(client, add):
    add("Thing")
    html = client.get("/").get_data(as_text=True)
    assert 'popovertarget="menu-1"' in html
    assert 'id="menu-1" popover' in html


# ---------- Board ----------

def test_board_columns(client, post, add):
    add("Plan", )
    add("Build", doing=1)
    add("Ship", completed=True)
    post("/view", {"view": "board"})
    html = client.get("/").get_data(as_text=True)
    todo, doing, done = (html.index(f'data-status="{key}"') for key in ["todo", "doing", "done"])
    assert todo < html.index("Plan") < doing < html.index("Build") < done < html.index("Ship")


@pytest.mark.parametrize("status, completed, doing", [
    ("doing", 0, 1),
    ("todo", 0, 0),
    ("done", 1, 0),
])
def test_move_between_columns(post, add, fetch, status, completed, doing):
    task_id = add("Build", doing=1)
    response = post(f"/tasks/{task_id}/status", {"status": status})
    assert response.status_code == 302
    task = fetch(task_id)
    assert (task["completed"], task["doing"]) == (completed, doing)


def test_done_back_to_doing(post, add, fetch):
    task_id = add("Ship", completed=True)
    post(f"/tasks/{task_id}/status", {"status": "doing"})
    task = fetch(task_id)
    assert (task["completed"], task["completed_at"], task["doing"]) == (0, None, 1)


def test_unknown_column_is_refused(post, add):
    task_id = add("Build")
    assert post(f"/tasks/{task_id}/status", {"status": "someday"}).status_code == 400


# ---------- Requests from JavaScript ----------

def test_fetch_requests_get_no_page_and_no_message(client, post, add, fetch):
    task_id = add("Swipe me")
    response = post(f"/tasks/{task_id}/toggle", headers=FETCH)
    assert response.status_code == 204
    assert response.data == b""
    assert fetch(task_id)["completed"] == 1
    assert "Completed “Swipe me”" not in client.get("/").get_data(as_text=True)


# ---------- Focus mode ----------

def titles_in_order(html, names):
    return sorted(names, key=html.index)


def test_focus_shows_open_tasks_most_important_first(client, add):
    # Titles that can't be confused with words on the page, like "Later".
    add("Task-no-date")
    add("Task-due-20th", due_date="2026-10-20")
    add("Task-important", priority=1)
    add("Task-due-10th", due_date="2026-10-10")
    add("Done already", completed=True)
    html = client.get("/focus").get_data(as_text=True)
    order = titles_in_order(html, ["Task-no-date", "Task-due-20th", "Task-important", "Task-due-10th"])
    assert order == ["Task-important", "Task-due-10th", "Task-due-20th", "Task-no-date"]
    assert "Done already" not in html
    assert "4 to go" in html


def test_focus_later_puts_a_task_at_the_back(client, add):
    first = add("Task-one", priority=1)
    second = add("Task-two")
    html = client.get(f"/focus?skip={first}").get_data(as_text=True)
    assert titles_in_order(html, ["Task-one", "Task-two"]) == ["Task-two", "Task-one"]
    # The Later button skips the new top card too.
    assert f'href="/focus?skip={first},{second}"' in html


def test_focus_buttons_act_on_the_top_card_and_come_back(post, add, fetch):
    task_id = add("Top", priority=1)
    response = post(f"/tasks/{task_id}/toggle", {"next": "focus"})
    assert response.headers["Location"] == "/focus"
    assert fetch(task_id)["completed"] == 1


def test_focus_all_clear(client, add):
    add("Done", completed=True)
    html = client.get("/focus").get_data(as_text=True)
    assert "All Clear!" in html
    assert "Go enjoy your day." in html


def test_all_clear_on_the_home_page_when_everything_is_done(client, add):
    add("Done", completed=True)
    html = client.get("/?status=active").get_data(as_text=True)
    assert "All Clear!" in html


# ---------- Undo ----------

def test_completing_shows_an_undo_toast(client, post, add):
    task_id = add("Thing")
    post(f"/tasks/{task_id}/toggle")
    html = client.get("/").get_data(as_text=True)
    assert "flash-undo" in html
    assert 'action="/undo"' in html


def test_undo_complete(post, add, fetch):
    task_id = add("Thing", doing=1)
    post(f"/tasks/{task_id}/toggle")
    post("/undo")
    task = fetch(task_id)
    assert (task["completed"], task["doing"]) == (0, 1)


def test_undo_complete_of_a_repeating_task_removes_the_copy(post, add, fetch):
    task_id = add("Daily", due_date="2026-10-19", repeat="day:1")
    post(f"/tasks/{task_id}/toggle")
    assert fetch(2) is not None  # the next copy
    post("/undo")
    assert fetch(2) is None
    task = fetch(task_id)
    assert (task["completed"], task["repeat"]) == (0, "day:1")


def test_undo_delete_brings_everything_back(client, post, app, fetch, tags_of):
    post("/tasks/new", {"title": "Trip", "tags": "travel", "subtasks": "passport\ncharger", "emoji": "✈️"})
    post("/subtasks/1/toggle")
    post("/tasks/1/delete")
    assert fetch(1) is None

    post("/undo")
    task = fetch(1)  # the same id as before
    assert (task["title"], task["emoji"]) == ("Trip", "✈️")
    assert tags_of(1) == ["travel"]
    assert subtasks_of(app, 1) == [{"title": "Passport", "done": 1}, {"title": "Charger", "done": 0}]
    assert "Brought back “Trip”." in client.get("/").get_data(as_text=True)


def test_undo_works_once(client, post, add, fetch):
    task_id = add("Thing")
    post(f"/tasks/{task_id}/delete")
    post("/undo")
    post("/undo")
    assert "There&#39;s nothing to undo." in client.get("/").get_data(as_text=True)


def test_undo_is_per_user(post, add, app, other_user):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO undo (user_id, data) VALUES (?, ?)",
                   (other_user, json.dumps({"action": "complete", "task_id": 99, "repeat": None,
                                            "doing": 0, "copy_id": None})))
        db.commit()
    post("/undo")  # alice has nothing to undo, and bob's stays
    assert len(rows(app, "SELECT * FROM undo WHERE user_id = ?", (other_user,))) == 1


def test_deleting_needs_no_confirm_popup(client, add):
    add("Thing")
    html = client.get("/").get_data(as_text=True)
    assert "confirm('Delete this task?" not in html
