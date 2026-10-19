"""Tests for validate_task(): plain function calls, no web server needed."""
from datetime import date

import pytest

from todo.validation import DESCRIPTION_MAX, TITLE_MAX, validate_task

TODAY = date(2026, 10, 19)


def test_valid_task_is_cleaned():
    data, errors = validate_task(
        {"title": "  Buy milk  ", "description": " 2 liters ", "due_date": "2026-10-20"}, TODAY
    )
    assert errors == {}
    assert data == {"title": "Buy milk", "description": "2 liters", "due_date": "2026-10-20"}


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
