"""Repeating tasks: reading rules like "every 2nd Monday" and working out
the next due date.

A rule is saved in the tasks.repeat column as a short code:

    "day:1"     every day              "day:3"    every 3 days
    "week:1"    every week             "week:2:0" every 2 weeks on Monday
    "month:1"   every month            "year:1"   every year
    "weekdays"  Monday to Friday
    "nth:2:0"   the 2nd Monday of every month ("nth:-1:4" = the last Friday)

Weekdays are numbered like Python's date.weekday(): 0 = Monday ... 6 = Sunday.
Like validation.py, nothing here uses Flask, so it's easy to test.
"""
import calendar
import re
from datetime import date, timedelta

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# Only full day names count. Short ones like "sun" or "sat" are also
# ordinary words, and "buy sun cream" shouldn't become a Sunday task.
WEEKDAY = "|".join(DAY_NAMES)
ORDINALS = {"1st": 1, "first": 1, "2nd": 2, "second": 2, "3rd": 3, "third": 3,
            "4th": 4, "fourth": 4, "last": -1}
ORDINAL_NAMES = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", -1: "last"}

# One pattern for every way of saying a repeat. The (?P<name>...) groups
# record which kind matched. quickadd.py searches for it inside a longer line.
REPEAT_PATTERN = re.compile(
    rf"""
    (?P<simple>daily|weekly|monthly|yearly|annually)
    | every\s+(?:
        (?P<nth>{"|".join(ORDINALS)})\s+(?P<nth_day>{WEEKDAY})
      | (?P<weekdays>weekdays?|work\s?days?)
      | (?:
            (?P<count>\d+)\s+(?P<units>days|weeks|months|years)
          | (?P<other>other\s+)?(?P<unit>day|week|month|year)
        )(?:\s+on\s+(?P<on_day>{WEEKDAY}))?
      | (?P<other_day>other\s+)?(?P<day>{WEEKDAY})
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

SIMPLE = {"daily": "day:1", "weekly": "week:1", "monthly": "month:1",
          "yearly": "year:1", "annually": "year:1"}


def day_number(name):
    return [d.lower() for d in DAY_NAMES].index(name.lower())


def rule_from_match(m):
    """Turn a REPEAT_PATTERN match into a rule code (None for "every 0 days")."""
    if m["simple"]:
        return SIMPLE[m["simple"].lower()]
    if m["nth"]:
        return f"nth:{ORDINALS[m['nth'].lower()]}:{day_number(m['nth_day'])}"
    if m["weekdays"]:
        return "weekdays"
    if m["day"]:
        return f"week:{2 if m['other_day'] else 1}:{day_number(m['day'])}"

    if m["count"]:
        count, unit = int(m["count"]), m["units"].lower()[:-1]  # "weeks" -> "week"
    else:
        count, unit = (2 if m["other"] else 1), m["unit"].lower()
    if count < 1:
        return None
    rule = f"{unit}:{count}"
    if unit == "week" and m["on_day"]:
        rule += f":{day_number(m['on_day'])}"
    return rule


def parse_repeat(text):
    """Read a repeat typed by the user, like "every 2 weeks". None if it isn't one."""
    m = REPEAT_PATTERN.fullmatch(text.strip())
    return rule_from_match(m) if m else None


def describe_repeat(rule):
    """The words for a rule code: "nth:2:0" -> "every 2nd Monday".

    parse_repeat() understands every description, so the edit form can show
    it and read it back.
    """
    kind, *numbers = rule.split(":")
    numbers = [int(n) for n in numbers]
    if kind == "weekdays":
        return "every weekday"
    if kind == "nth":
        return f"every {ORDINAL_NAMES[numbers[0]]} {DAY_NAMES[numbers[1]]}"
    count = numbers[0]
    if kind == "week" and len(numbers) == 2:
        day = DAY_NAMES[numbers[1]]
        return f"every {day}" if count == 1 else f"every {count} weeks on {day}"
    return f"every {kind}" if count == 1 else f"every {count} {kind}s"


# ---------- Date arithmetic ----------

def add_months(day, months):
    """The same day of the month, `months` later. Jan 31 + 1 month = Feb 28."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def nth_weekday(year, month, n, weekday):
    """The nth `weekday` of a month, e.g. the 2nd Monday. n = -1 means the last one."""
    if n == -1:
        last = date(year, month, calendar.monthrange(year, month)[1])
        return last - timedelta(days=(last.weekday() - weekday) % 7)
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7, weeks=n - 1)


def next_due(rule, due):
    """The first date the rule gives after `due`."""
    kind, *numbers = rule.split(":")
    numbers = [int(n) for n in numbers]
    if kind == "day":
        return due + timedelta(days=numbers[0])
    if kind == "week":
        return due + timedelta(weeks=numbers[0])
    if kind == "month":
        return add_months(due, numbers[0])
    if kind == "year":
        return add_months(due, 12 * numbers[0])
    if kind == "weekdays":
        due += timedelta(days=1)
        while due.weekday() >= 5:  # 5 and 6 are Saturday and Sunday
            due += timedelta(days=1)
        return due
    if kind == "nth":
        n, weekday = numbers
        # Every month has at least four of each weekday, so this month's or
        # next month's is always the answer.
        for months_ahead in (0, 1):
            month_start = add_months(due.replace(day=1), months_ahead)
            day = nth_weekday(month_start.year, month_start.month, n, weekday)
            if day > due:
                return day
    raise ValueError(f"Unknown repeat rule: {rule}")


def first_due(rule, today):
    """The first date on or after today that fits the rule.

    Used when a repeating task is given no date: "every Friday" starts on
    the coming Friday, "every day" starts today.
    """
    kind, *numbers = rule.split(":")
    if kind == "week" and len(numbers) == 2:
        return today + timedelta(days=(int(numbers[1]) - today.weekday()) % 7)
    if kind in ("weekdays", "nth"):
        return next_due(rule, today - timedelta(days=1))
    return today


def next_due_after(rule, due, today):
    """The due date for the next copy of a repeating task that was just done.

    It's one step after the old due date. If that's still today or earlier
    (the task was done late), keep stepping, so finishing an old task
    doesn't immediately create another overdue one.
    """
    day = next_due(rule, due)
    while day <= today:
        day = next_due(rule, day)
    return day
