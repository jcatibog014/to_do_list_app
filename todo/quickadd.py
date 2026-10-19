"""Quick add: turn one typed line like "pay rent friday 5pm #home" into a task.

parse_quick_add() looks for a repeat, a date, a time and #tags. It cuts
each one it finds out of the text, and whatever is left is the title.
Like validation.py, nothing here uses Flask.
"""
import re
from datetime import date, timedelta

from .recurrence import REPEAT_PATTERN, WEEKDAY, add_months, day_number, rule_from_match

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH = (r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?"
         r"|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?")
SUFFIX = r"(?:st|nd|rd|th)?"  # the "th" in "25th"


def whole_words(pattern):
    """Match `pattern` only as whole words, so "today" isn't found inside
    "today's" and "may 5" isn't found inside "dismay 5".

    re.VERBOSE lets the patterns below spread over several lines: spaces
    in them are ignored, so a real space is written as \\s.
    """
    return re.compile(rf"(?<![\w#'’])(?:{pattern})(?![\w'’-])", re.IGNORECASE | re.VERBOSE)


REPEAT = whole_words(REPEAT_PATTERN.pattern)
DATE = whole_words(rf"""(?:(?:on|by|due|from|starting)\s+)?(?:
    (?P<today>today|tonight)
  | (?P<tomorrow>tomorrow|tmrw|tmr)
  | (?P<next>next\s+)?(?P<day>{WEEKDAY})
  | next\s+(?P<next_unit>week|month)
  | in\s+(?P<count>\d+)\s+(?P<unit>days?|weeks?|months?)
  | (?P<month>{MONTH})\.?\s+(?P<month_day>\d{{1,2}}){SUFFIX}(?:,?\s+(?P<year>\d{{4}}))?
  | (?P<day_first>\d{{1,2}}){SUFFIX}\s+(?P<month2>{MONTH})(?:\s+(?P<year2>\d{{4}}))?
  | (?P<iso>\d{{4}}-\d{{2}}-\d{{2}})
)""")
TIME = whole_words(r"""(?:at\s+|@\s*)?(?:
    (?P<hour>\d{1,2})(?::(?P<minute>[0-5]\d))?\s*(?P<ampm>am|pm|a\.m\.|p\.m\.)
  | (?P<hour24>[01]?\d|2[0-3]):(?P<minute24>[0-5]\d)
  | (?P<noon>noon)
)""")
TAG = re.compile(r"(?<![\w&])#(\w[\w-]*)")


def parse_quick_add(text, today):
    """Split a quick-add line into its parts.

    Returns a dict with "title", "due_date" ('YYYY-MM-DD'), "due_time"
    ('HH:MM'), "repeat" (a rule code from recurrence.py) and "tags" (a
    list). Parts that weren't typed are None, or [] for tags. Checking the
    values, like whether "feb 30" exists, is left to validate_task().
    """
    result = {"due_date": None, "due_time": None, "repeat": None, "tags": []}

    # Repeats go first: "every friday" holds a day name that DATE would
    # otherwise take as a one-off date.
    match = REPEAT.search(text)
    if match:
        result["repeat"] = rule_from_match(match)
        text = cut(text, match)

    match = DATE.search(text)
    if match:
        result["due_date"] = date_from_match(match, today)
        text = cut(text, match)

    match = TIME.search(text)
    if match:
        result["due_time"] = time_from_match(match)
        text = cut(text, match)
        # "call mom 5pm" with no day means today. A repeating task without
        # a day gets its first date from the rule instead, in validate_task().
        if result["due_date"] is None and result["due_time"] and not result["repeat"]:
            result["due_date"] = today.isoformat()

    result["tags"] = [tag.lower() for tag in TAG.findall(text)]
    text = TAG.sub("", text)

    # Tidy what's left: single spaces, and no stray commas at the ends.
    result["title"] = " ".join(text.split()).strip(" ,;-")
    return result


def cut(text, match):
    return text[:match.start()] + " " + text[match.end():]


def date_from_match(m, today):
    if m["today"]:
        day = today
    elif m["tomorrow"]:
        day = today + timedelta(days=1)
    elif m["day"]:
        # The coming one: "friday" on a Friday means today. "next friday"
        # is the one a week after that.
        day = today + timedelta(days=(day_number(m["day"]) - today.weekday()) % 7)
        if m["next"]:
            day += timedelta(weeks=1)
    elif m["next_unit"]:
        day = today + timedelta(weeks=1) if m["next_unit"].lower() == "week" else add_months(today, 1)
    elif m["count"]:
        count, unit = int(m["count"]), m["unit"].lower().rstrip("s")
        if unit == "day":
            day = today + timedelta(days=count)
        elif unit == "week":
            day = today + timedelta(weeks=count)
        else:
            day = add_months(today, count)
    elif m["iso"]:
        return m["iso"]  # validate_task() checks that it's a real date
    else:
        month_name = m["month"] or m["month2"]
        month = MONTHS.index(month_name[:3].lower()) + 1
        day_of_month = int(m["month_day"] or m["day_first"])
        year = m["year"] or m["year2"]
        try:
            day = date(int(year) if year else today.year, month, day_of_month)
        except ValueError:
            # "feb 30": hand it on as text, and validate_task() will say
            # that the date doesn't exist.
            return f"{year or today.year}-{month:02d}-{day_of_month:02d}"
        # "jan 5" typed in October means next January.
        if not year and day < today:
            day = day.replace(year=today.year + 1)
    return day.isoformat()


def time_from_match(m):
    """'HH:MM' on a 24-hour clock, or None for an impossible time like "13pm"."""
    if m["noon"]:
        return "12:00"
    if m["hour24"]:
        return f"{int(m['hour24']):02d}:{m['minute24']}"
    hour, minute = int(m["hour"]), m["minute"] or "00"
    if not 1 <= hour <= 12:
        return None
    pm = m["ampm"].lower().startswith("p")
    # 12am is midnight (00) and 12pm is noon (12).
    hour = hour % 12 + (12 if pm else 0)
    return f"{hour:02d}:{minute}"
