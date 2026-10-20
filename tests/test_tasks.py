"""Tests for the pages and actions, using Flask's test client.

The test client sends fake requests to the app, without a browser or a
running server, and gives back the response.
"""
import pytest


# ---------- Read ----------

def test_empty_list(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "No tasks yet" in response.get_data(as_text=True)


def test_titles_are_html_escaped(client, add):
    add("<script>alert(1)</script>")
    html = client.get("/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_unfinished_tasks_come_first_then_by_due_date(client, add):
    add("Done task", due_date="2026-10-19", completed=True)
    add("No date")
    add("Further off", due_date="2026-12-01")
    add("Sooner", due_date="2026-10-20")
    html = client.get("/").get_data(as_text=True)
    positions = [html.index(t) for t in ["Sooner", "Further off", "No date", "Done task"]]
    assert positions == sorted(positions)


# ---------- Create ----------

def test_new_task_form(client):
    response = client.get("/tasks/new")
    assert response.status_code == 200
    assert 'name="title"' in response.get_data(as_text=True)


def test_create_task(client, post, fetch):
    response = post("/tasks/new", {"title": "Buy milk", "due_date": "2026-10-20"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/"

    task = fetch(1)
    assert task["title"] == "Buy milk"
    assert task["due_date"] == "2026-10-20"
    assert task["completed"] == 0

    html = client.get("/").get_data(as_text=True)
    assert "Buy milk" in html
    assert "Due tomorrow" in html
    assert "Added “Buy milk”." in html  # the flash message


def test_create_without_due_date_saves_null(post, fetch):
    post("/tasks/new", {"title": "Someday", "due_date": ""})
    assert fetch(1)["due_date"] is None


def test_invalid_create_shows_errors_and_saves_nothing(client, post, fetch):
    response = post("/tasks/new", {"title": "   ", "description": "keep me", "due_date": "2026-10-01"})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "Title is required." in html
    assert "Due date can&#39;t be in the past." in html
    assert "keep me" in html  # what the user typed is kept
    assert fetch(1) is None


# ---------- Update ----------

def test_edit_form_is_prefilled(client, add):
    task_id = add("Old title", description="Old notes")
    html = client.get(f"/tasks/{task_id}/edit").get_data(as_text=True)
    assert 'value="Old title"' in html
    assert "Old notes" in html


def test_edit_task(post, add, fetch):
    task_id = add("Old title")
    response = post(f"/tasks/{task_id}/edit", {"title": "New title", "description": "notes", "due_date": "2026-11-01"})
    assert response.status_code == 302
    task = fetch(task_id)
    assert (task["title"], task["description"], task["due_date"]) == ("New title", "notes", "2026-11-01")


def test_edit_can_keep_a_past_due_date(post, add, fetch):
    task_id = add("Late", due_date="2026-10-01")
    response = post(f"/tasks/{task_id}/edit", {"title": "Late!", "due_date": "2026-10-01"})
    assert response.status_code == 302
    assert fetch(task_id)["title"] == "Late!"


def test_invalid_edit_changes_nothing(post, add, fetch):
    task_id = add("Keep me")
    response = post(f"/tasks/{task_id}/edit", {"title": ""})
    assert response.status_code == 400
    assert fetch(task_id)["title"] == "Keep me"


def test_toggle_complete_and_back(post, add, fetch):
    task_id = add("Walk the dog")

    post(f"/tasks/{task_id}/toggle")
    task = fetch(task_id)
    assert task["completed"] == 1
    assert task["completed_at"] is not None

    post(f"/tasks/{task_id}/toggle")
    task = fetch(task_id)
    assert task["completed"] == 0
    assert task["completed_at"] is None


# ---------- Delete ----------

def test_delete_task(post, add, fetch):
    task_id = add("Trash me")
    response = post(f"/tasks/{task_id}/delete")
    assert response.status_code == 302
    assert fetch(task_id) is None


# ---------- Filters and search ----------

@pytest.fixture
def mixed_tasks(add):
    add("Alpha active, no date")
    add("Bravo due today", due_date="2026-10-19")
    add("Charlie overdue", due_date="2026-10-10")
    add("Delta finished", due_date="2026-10-10", completed=True)


@pytest.mark.parametrize("status, expected", [
    ("all", {"Alpha", "Bravo", "Charlie", "Delta"}),
    ("active", {"Alpha", "Bravo", "Charlie"}),
    ("today", {"Bravo", "Charlie"}),  # Today shows late tasks too
    ("overdue", {"Charlie"}),  # Delta is past due too, but it's done
    ("completed", {"Delta"}),
    ("nonsense", {"Alpha", "Bravo", "Charlie", "Delta"}),  # unknown filter = all
])
def test_filters(client, mixed_tasks, status, expected):
    html = client.get(f"/?status={status}").get_data(as_text=True)
    shown = {name for name in ["Alpha", "Bravo", "Charlie", "Delta"] if name in html}
    assert shown == expected


def test_tab_counts(client, mixed_tasks):
    html = client.get("/").get_data(as_text=True)
    assert 'Active <span class="count">3</span>' in html
    assert 'Completed <span class="count">1</span>' in html


def test_search_matches_title_and_description_ignoring_case(client, add):
    add("Buy MILK")
    add("Groceries", description="eggs and milk")
    add("Call the bank")
    html = client.get("/?q=milk").get_data(as_text=True)
    assert "Buy MILK" in html
    assert "Groceries" in html
    assert "Call the bank" not in html


def test_actions_return_to_the_same_filter(post, add):
    task_id = add("Task")
    response = post(f"/tasks/{task_id}/toggle?status=active&q=ta")
    assert response.headers["Location"] == "/?status=active&q=ta"


# ---------- Errors ----------

@pytest.mark.parametrize("method, url", [
    ("get", "/tasks/99/edit"),
    ("post", "/tasks/99/edit"),
    ("post", "/tasks/99/toggle"),
    ("post", "/tasks/99/delete"),
])
def test_missing_task_is_404(client, post, method, url):
    response = client.get(url) if method == "get" else post(url, {"title": "x"})
    assert response.status_code == 404
    assert "Task 99 doesn" in response.get_data(as_text=True)


def test_post_without_csrf_token_is_refused(client, add, fetch):
    task_id = add("Safe")
    response = client.post(f"/tasks/{task_id}/delete")
    assert response.status_code == 400
    assert fetch(task_id) is not None


def test_post_with_wrong_csrf_token_is_refused(client, add, fetch):
    task_id = add("Safe")
    response = client.post(f"/tasks/{task_id}/delete", data={"csrf_token": "guess"})
    assert response.status_code == 400
    assert fetch(task_id) is not None
