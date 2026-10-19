"""Tests for repeat rules: reading them, describing them and stepping dates."""
from datetime import date

import pytest

from todo.recurrence import (
    add_months,
    describe_repeat,
    first_due,
    next_due,
    next_due_after,
    nth_weekday,
    parse_repeat,
)

MONDAY = date(2026, 10, 19)  # the fixed "today" used in every test


@pytest.mark.parametrize("text, rule", [
    ("daily", "day:1"),
    ("every day", "day:1"),
    ("Every Other Day", "day:2"),
    ("every 3 days", "day:3"),
    ("weekly", "week:1"),
    ("every 2 weeks", "week:2"),
    ("every friday", "week:1:4"),
    ("every other wednesday", "week:2:2"),
    ("every 2 weeks on monday", "week:2:0"),
    ("every weekday", "weekdays"),
    ("every workday", "weekdays"),
    ("monthly", "month:1"),
    ("every 6 months", "month:6"),
    ("every 2nd monday", "nth:2:0"),
    ("every first friday", "nth:1:4"),
    ("every last sunday", "nth:-1:6"),
    ("yearly", "year:1"),
    ("annually", "year:1"),
])
def test_parse_repeat(text, rule):
    assert parse_repeat(text) == rule


@pytest.mark.parametrize("text", ["", "sometimes", "every", "every 0 days", "every fri", "every 5th monday"])
def test_parse_repeat_rejects_other_text(text):
    assert parse_repeat(text) is None


@pytest.mark.parametrize("rule, text", [
    ("day:1", "every day"),
    ("day:3", "every 3 days"),
    ("week:1", "every week"),
    ("week:1:0", "every Monday"),
    ("week:2:4", "every 2 weeks on Friday"),
    ("weekdays", "every weekday"),
    ("month:1", "every month"),
    ("nth:2:0", "every 2nd Monday"),
    ("nth:-1:4", "every last Friday"),
    ("year:2", "every 2 years"),
])
def test_describe_repeat_and_read_it_back(rule, text):
    assert describe_repeat(rule) == text
    # The edit form shows the description, so it must parse back to the same rule.
    assert parse_repeat(text) == rule


def test_add_months_keeps_the_day_or_uses_the_last_one():
    assert add_months(date(2026, 10, 19), 1) == date(2026, 11, 19)
    assert add_months(date(2026, 12, 5), 1) == date(2027, 1, 5)
    assert add_months(date(2027, 1, 31), 1) == date(2027, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)  # leap year


def test_nth_weekday():
    assert nth_weekday(2026, 10, 2, 0) == date(2026, 10, 12)   # 2nd Monday of Oct 2026
    assert nth_weekday(2026, 10, -1, 4) == date(2026, 10, 30)  # last Friday
    assert nth_weekday(2026, 11, 1, 6) == date(2026, 11, 1)    # 1st Sunday is the 1st


@pytest.mark.parametrize("rule, due, expected", [
    ("day:1", date(2026, 10, 19), date(2026, 10, 20)),
    ("day:3", date(2026, 10, 30), date(2026, 11, 2)),
    ("week:2:0", date(2026, 10, 19), date(2026, 11, 2)),
    ("month:1", date(2026, 10, 31), date(2026, 11, 30)),
    ("year:1", date(2028, 2, 29), date(2029, 2, 28)),
    ("weekdays", date(2026, 10, 23), date(2026, 10, 26)),  # Friday -> Monday
    ("weekdays", date(2026, 10, 19), date(2026, 10, 20)),
    ("nth:2:0", date(2026, 10, 12), date(2026, 11, 9)),
    ("nth:2:0", date(2026, 10, 5), date(2026, 10, 12)),  # this month's is still ahead
    ("nth:-1:4", date(2026, 10, 30), date(2026, 11, 27)),
])
def test_next_due(rule, due, expected):
    assert next_due(rule, due) == expected


@pytest.mark.parametrize("rule, expected", [
    ("day:1", MONDAY),
    ("week:1", MONDAY),
    ("week:1:0", MONDAY),               # every Monday, and today is Monday
    ("week:1:4", date(2026, 10, 23)),   # every Friday
    ("weekdays", MONDAY),
    ("nth:2:0", date(2026, 11, 9)),     # October's 2nd Monday has passed
    ("nth:-1:4", date(2026, 10, 30)),
])
def test_first_due(rule, expected):
    assert first_due(rule, MONDAY) == expected


def test_next_due_after_done_early_or_on_time():
    assert next_due_after("week:1", date(2026, 10, 23), MONDAY) == date(2026, 10, 30)
    assert next_due_after("day:1", MONDAY, MONDAY) == date(2026, 10, 20)


def test_next_due_after_done_late_skips_past_dates():
    # A daily task 5 days late: the next one is tomorrow, not 4 days ago.
    assert next_due_after("day:1", date(2026, 10, 14), MONDAY) == date(2026, 10, 20)
    # Weekly from a Wednesday, 2 weeks late: still on Wednesdays.
    assert next_due_after("week:1", date(2026, 10, 7), MONDAY) == date(2026, 10, 21)
