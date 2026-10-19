"""Tests for parse_quick_add(): one typed line in, the parts of a task out."""
from datetime import date

import pytest

from todo.quickadd import parse_quick_add

MONDAY = date(2026, 10, 19)  # the fixed "today" used in every test


def parse(text):
    return parse_quick_add(text, MONDAY)


def test_plain_text_is_just_a_title():
    assert parse("Buy milk") == {
        "title": "Buy milk", "due_date": None, "due_time": None, "repeat": None, "tags": [],
        "priority": False, "emoji": None,
    }


def test_the_example_from_the_feature_request():
    result = parse("pay rent friday 5pm")
    assert result["title"] == "pay rent"
    assert result["due_date"] == "2026-10-23"
    assert result["due_time"] == "17:00"


@pytest.mark.parametrize("text, due", [
    ("call mom today", "2026-10-19"),
    ("call mom tonight", "2026-10-19"),
    ("call mom tomorrow", "2026-10-20"),
    ("call mom tmrw", "2026-10-20"),
    ("call mom monday", "2026-10-19"),        # today is Monday
    ("call mom on Wednesday", "2026-10-21"),
    ("call mom next friday", "2026-10-30"),
    ("call mom next week", "2026-10-26"),
    ("call mom next month", "2026-11-19"),
    ("call mom in 3 days", "2026-10-22"),
    ("call mom in 1 week", "2026-10-26"),
    ("call mom in 2 months", "2026-12-19"),
    ("call mom oct 25", "2026-10-25"),
    ("call mom October 25th", "2026-10-25"),
    ("call mom 25 dec", "2026-12-25"),
    ("call mom jan 5", "2027-01-05"),         # January has passed this year
    ("call mom mar 3, 2028", "2028-03-03"),
    ("call mom 2026-11-30", "2026-11-30"),
    ("call mom by friday", "2026-10-23"),
])
def test_dates(text, due):
    result = parse(text)
    assert result["due_date"] == due
    assert result["title"] == "call mom"


@pytest.mark.parametrize("text, time", [
    ("gym 6am", "06:00"),
    ("gym 6 AM", "06:00"),
    ("gym at 5:30pm", "17:30"),
    ("gym 12am", "00:00"),
    ("gym 12pm", "12:00"),
    ("gym noon", "12:00"),
    ("gym 17:45", "17:45"),
    ("gym @ 7pm", "19:00"),
])
def test_times(text, time):
    result = parse(text)
    assert result["due_time"] == time
    assert result["title"] == "gym"


def test_a_time_alone_means_today():
    assert parse("call mom 5pm")["due_date"] == "2026-10-19"


def test_repeats_and_their_date_is_left_to_validation():
    result = parse("team meeting every 2nd monday 10:30am")
    assert result == {
        "title": "team meeting", "due_date": None, "due_time": "10:30",
        "repeat": "nth:2:0", "tags": [], "priority": False, "emoji": None,
    }


def test_repeat_with_a_start_date():
    result = parse("water plants every 3 days starting nov 1")
    assert result["title"] == "water plants"
    assert result["repeat"] == "day:3"
    assert result["due_date"] == "2026-11-01"


def test_tags():
    result = parse("buy paint #Home #diy-projects")
    assert result["title"] == "buy paint"
    assert result["tags"] == ["home", "diy-projects"]


def test_everything_at_once():
    result = parse("Pay rent every month oct 31 9am #home #bills")
    assert result == {
        "title": "Pay rent", "due_date": "2026-10-31", "due_time": "09:00",
        "repeat": "month:1", "tags": ["home", "bills"], "priority": False, "emoji": None,
    }


@pytest.mark.parametrize("text", [
    "review today's notes",   # "today" inside "today's"
    "buy sun cream",          # "sun" isn't Sunday
    "learn C# basics",        # "C#" isn't a tag
    "read chapter 5",         # a number isn't a time
    "every weekend chores",   # "every week" inside "every weekend"
    "dismay 5",               # "may 5" inside "dismay 5"
])
def test_ordinary_words_are_left_alone(text):
    result = parse(text)
    assert result["title"] == text
    assert (result["due_date"], result["due_time"], result["repeat"], result["tags"]) == (None, None, None, [])


def test_impossible_dates_and_times_are_passed_on_for_validation():
    assert parse("party feb 30")["due_date"] == "2026-02-30"
    assert parse("party 13pm")["due_time"] is None


def test_only_a_date_leaves_an_empty_title():
    assert parse("tomorrow 5pm")["title"] == ""


@pytest.mark.parametrize("text", ["call mom !", "! call mom", "call mom !high", "call mom !!"])
def test_exclamation_mark_means_high_priority(text):
    result = parse(text)
    assert result["priority"] is True
    assert result["title"] == "call mom"


def test_exclamation_inside_a_word_is_kept():
    result = parse("yay! done")
    assert result["priority"] is False
    assert result["title"] == "yay! done"


@pytest.mark.parametrize("text, emoji", [
    ("🛒 buy eggs", "🛒"),
    ("buy eggs 🛒", "🛒"),
    ("❤️ call grandma", "❤️"),
    ("✈️ pack bags", "✈️"),
    ("👩‍💻 code review", "👩‍💻"),   # several emoji glued together with \u200d
])
def test_emoji_is_taken_out_of_the_title(text, emoji):
    result = parse(text)
    assert result["emoji"] == emoji
    assert "🛒" not in result["title"] and result["title"].strip() == result["title"]
