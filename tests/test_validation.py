"""Tests for validate_task() and validate_registration(): plain function calls, no web server needed."""
from datetime import date

import pytest

from todo.validation import (
    DESCRIPTION_MAX,
    LIST_COLORS,
    PASSWORD_MIN,
    TITLE_MAX,
    USERNAME_MAX,
    next_list_color,
    validate_list_color,
    validate_list_name,
    validate_registration,
    validate_task,
)

TODAY = date(2026, 10, 19)


def test_valid_task_is_cleaned():
    data, errors = validate_task(
        {"title": "  Buy milk  ", "description": " 2 liters ", "due_date": "2026-10-20"}, TODAY
    )
    assert errors == {}
    assert data == {
        "title": "Buy milk", "description": "2 liters", "due_date": "2026-10-20",
        "due_time": None, "repeat": None, "remind_before": None, "tags": [], "list_id": None,
    }


def test_only_title_is_required():
    data, errors = validate_task({"title": "Call mom"}, TODAY)
    assert errors == {}
    assert data["description"] == ""
    assert data["due_date"] is None


@pytest.mark.parametrize("title", ["", "   ", "\t\n"])
def test_blank_title_is_rejected(title):
    _, errors = validate_task({"title": title}, TODAY)
    assert errors["title"] == "Title is required."


def test_title_length_limit():
    _, errors = validate_task({"title": "x" * TITLE_MAX}, TODAY)
    assert "title" not in errors

    _, errors = validate_task({"title": "x" * (TITLE_MAX + 1)}, TODAY)
    assert "100 characters or fewer" in errors["title"]


def test_description_length_limit():
    _, errors = validate_task({"title": "ok", "description": "x" * (DESCRIPTION_MAX + 1)}, TODAY)
    assert "description" in errors


@pytest.mark.parametrize("bad", ["tomorrow", "19/10/2026", "2026-1-5", "20261020"])
def test_due_date_must_be_yyyy_mm_dd(bad):
    _, errors = validate_task({"title": "ok", "due_date": bad}, TODAY)
    assert errors["due_date"] == "Enter the date as YYYY-MM-DD."


@pytest.mark.parametrize("impossible", ["2026-02-30", "2026-13-01", "2026-11-31"])
def test_due_date_must_exist(impossible):
    _, errors = validate_task({"title": "ok", "due_date": impossible}, TODAY)
    assert errors["due_date"] == "That date doesn't exist."


def test_due_date_today_is_allowed():
    _, errors = validate_task({"title": "ok", "due_date": "2026-10-19"}, TODAY)
    assert errors == {}


def test_past_due_date_is_rejected_for_new_tasks():
    _, errors = validate_task({"title": "ok", "due_date": "2026-10-18"}, TODAY)
    assert errors["due_date"] == "Due date can't be in the past."


def test_editing_keeps_an_existing_past_due_date():
    form = {"title": "renamed", "due_date": "2026-10-01"}
    _, errors = validate_task(form, TODAY, existing_due_date="2026-10-01")
    assert errors == {}


def test_editing_cannot_move_due_date_to_another_past_day():
    form = {"title": "renamed", "due_date": "2026-09-30"}
    _, errors = validate_task(form, TODAY, existing_due_date="2026-10-01")
    assert "due_date" in errors


def test_several_errors_are_reported_together():
    _, errors = validate_task({"title": "", "due_date": "nope"}, TODAY)
    assert set(errors) == {"title", "due_date"}


# ---------- Sign-up form ----------

def signup(username="new_user", password="secret123", confirm=None):
    # By default the confirm box matches the password, like a careful user.
    return {"username": username, "password": password,
            "confirm": password if confirm is None else confirm}


def test_valid_signup_is_cleaned():
    data, errors = validate_registration(signup(username="  ana_99  "))
    assert errors == {}
    assert data == {"username": "ana_99", "password": "secret123"}


def test_password_spaces_are_kept():
    data, _ = validate_registration(signup(password=" spaced out "))
    assert data["password"] == " spaced out "


@pytest.mark.parametrize("username, message", [
    ("", "Username is required."),
    ("   ", "Username is required."),
    ("ab", "Use 3 to 30 letters, numbers or underscores (_)."),
    ("x" * (USERNAME_MAX + 1), "Use 3 to 30 letters, numbers or underscores (_)."),
    ("ana maria", "Use 3 to 30 letters, numbers or underscores (_)."),
    ("ana@mail", "Use 3 to 30 letters, numbers or underscores (_)."),
])
def test_bad_usernames_are_rejected(username, message):
    _, errors = validate_registration(signup(username=username))
    assert errors["username"] == message


def test_username_length_limits_are_inclusive():
    for name in ["abc", "x" * USERNAME_MAX]:
        _, errors = validate_registration(signup(username=name))
        assert "username" not in errors


def test_password_minimum_length():
    _, errors = validate_registration(signup(password="x" * PASSWORD_MIN))
    assert errors == {}

    _, errors = validate_registration(signup(password="x" * (PASSWORD_MIN - 1)))
    assert errors["password"] == "Password must be at least 8 characters."


def test_passwords_must_match():
    _, errors = validate_registration(signup(password="secret123", confirm="secret124"))
    assert errors == {"confirm": "The passwords don't match."}


# ---------- Time, repeat, reminder, tags and list ----------

def full(**fields):
    """A valid task form, with some fields changed."""
    return {"title": "ok", "due_date": "2026-10-20", **fields}


def test_all_new_fields_are_cleaned():
    form = full(due_time="17:30", repeat=" Every 2nd Monday ", remind_before="10",
                tags="#Home, errands  home", list_id="3")
    data, errors = validate_task(form, TODAY)
    assert errors == {}
    assert data["due_time"] == "17:30"
    assert data["repeat"] == "nth:2:0"
    assert data["remind_before"] == 10
    assert data["tags"] == ["home", "errands"]  # lowercase, no #, no repeats
    assert data["list_id"] == 3


@pytest.mark.parametrize("bad", ["5pm", "24:00", "7:30", "17:60"])
def test_time_must_be_hh_mm(bad):
    _, errors = validate_task(full(due_time=bad), TODAY)
    assert errors["due_time"] == "Enter the time as HH:MM, like 17:30."


def test_time_needs_a_date():
    _, errors = validate_task({"title": "ok", "due_time": "09:00"}, TODAY)
    assert errors == {"due_time": "Add a due date for this time."}


def test_unknown_repeat_is_rejected():
    _, errors = validate_task(full(repeat="whenever"), TODAY)
    assert "every 2nd Monday" in errors["repeat"]


def test_repeat_without_date_starts_on_the_first_matching_day():
    # TODAY is a Monday, so "every Friday" starts on Friday the 23rd.
    data, errors = validate_task({"title": "ok", "repeat": "every friday"}, TODAY)
    assert errors == {}
    assert data["due_date"] == "2026-10-23"


@pytest.mark.parametrize("remind, message", [
    ("15", "Choose a reminder from the list."),
    ("soon", "Choose a reminder from the list."),
    ("0", "Set a due time to get a reminder."),
])
def test_bad_reminders(remind, message):
    _, errors = validate_task(full(remind_before=remind), TODAY)
    assert errors["remind_before"] == message


def test_reminder_at_the_due_time_is_zero_minutes():
    data, errors = validate_task(full(due_time="08:00", remind_before="0"), TODAY)
    assert errors == {}
    assert data["remind_before"] == 0


def test_bad_tags():
    _, errors = validate_task(full(tags="ok no!pe"), TODAY)
    assert "Tags can use letters" in errors["tags"]

    _, errors = validate_task(full(tags=" ".join(f"t{n}" for n in range(11))), TODAY)
    assert errors["tags"] == "Use 10 tags or fewer."


def test_list_id_must_be_a_number():
    _, errors = validate_task(full(list_id="work"), TODAY)
    assert errors["list_id"] == "Choose a list from the menu."


# ---------- List names ----------

def test_list_name_is_tidied():
    assert validate_list_name({"name": "  Home   stuff "}) == ("Home stuff", None)


def test_bad_list_names():
    assert validate_list_name({"name": "   "})[1] == "Give the list a name."
    assert "40 characters" in validate_list_name({"name": "x" * 41})[1]


# ---------- List colors ----------

def test_list_color():
    assert validate_list_color({"color": "teal"}) == ("teal", None)
    assert validate_list_color({"color": "plaid"}) == (None, "Pick one of the colors.")
    assert validate_list_color({}) == (None, "Pick one of the colors.")
    assert validate_list_color({}, default="green") == ("green", None)


def test_next_list_color_goes_round_the_palette():
    assert next_list_color(0) == LIST_COLORS[0]
    assert next_list_color(1) == LIST_COLORS[1]
    assert next_list_color(len(LIST_COLORS)) == LIST_COLORS[0]
