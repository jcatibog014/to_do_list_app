"""The Calendar and Stats pages. (Theme settings are on the profile page, in profile.py.)"""
import calendar as cal
from collections import Counter
from datetime import date, timedelta

from flask import Blueprint, g, render_template, request

from .auth import require_login
from .db import get_db
from .recurrence import add_months
from .tasks import decorate, today, user_lists

bp = Blueprint("pages", __name__)
bp.before_request(require_login)

WEEKDAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


# ---------- Calendar ----------

@bp.get("/calendar")
def calendar():
    """A month of days, each with the tasks due on it.

    ?month=2026-10 picks the month, and ?day=2026-10-23 opens one day's tasks.
    """
    now = today()
    try:
        first = date.fromisoformat(request.args.get("month", "") + "-01")
    except ValueError:
        first = now.replace(day=1)

    # monthdatescalendar() gives whole weeks (Sunday first, from
    # firstweekday=6), so the grid starts and ends with a few days of the
    # months around this one.
    weeks = cal.Calendar(firstweekday=6).monthdatescalendar(first.year, first.month)
    start, end = weeks[0][0], weeks[-1][-1]
    rows = get_db().execute(
        "SELECT * FROM tasks WHERE user_id = ? AND due_date BETWEEN ? AND ?"
        " ORDER BY completed, due_time IS NULL, due_time, id",
        (g.user["id"], start.isoformat(), end.isoformat()),
    ).fetchall()
    by_day = {}
    for task in decorate(rows, now):
        by_day.setdefault(task["due_date"], []).append(task)

    # The day whose tasks are listed under the grid: the one asked for, or
    # today when this month is on screen.
    try:
        selected = date.fromisoformat(request.args.get("day", ""))
    except ValueError:
        selected = now if (now.year, now.month) == (first.year, first.month) else None
    if selected and not start <= selected <= end:
        selected = None

    return render_template(
        "calendar.html", weeks=weeks, by_day=by_day, first=first, now=now,
        selected=selected, selected_tasks=by_day.get(selected.isoformat(), []) if selected else [],
        prev_month=add_months(first, -1), next_month=add_months(first, 1),
        weekday_names=WEEKDAY_NAMES, lists=user_lists(),
    )


# ---------- Stats ----------

def streaks(days, today):
    """Return (current, best): runs of days in a row with a task done.

    days is a set of dates. The current streak still counts if today has
    nothing done yet but yesterday did: the day isn't over.
    """
    best = run = 0
    previous = None
    for day in sorted(days):
        run = run + 1 if previous and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day

    current = 0
    day = today if today in days else today - timedelta(days=1)
    while day in days:
        current += 1
        day -= timedelta(days=1)
    return current, best


def user_streaks():
    """The logged-in user's (current, best) streaks, and a Counter of tasks done per day."""
    rows = get_db().execute(
        "SELECT completed_at FROM tasks WHERE user_id = ? AND completed = 1 AND completed_at IS NOT NULL",
        (g.user["id"],),
    ).fetchall()
    # completed_at looks like '2026-10-19 14:05:00'. The first 10 characters are the date.
    done_per_day = Counter(date.fromisoformat(row["completed_at"][:10]) for row in rows)
    return streaks(set(done_per_day), today()), done_per_day


@bp.get("/stats")
def stats():
    now = today()
    (current, best), done_per_day = user_streaks()
    tasks = get_db().execute(
        "SELECT completed, due_date, list_id FROM tasks WHERE user_id = ?", (g.user["id"],)
    ).fetchall()
    open_tasks = [t for t in tasks if not t["completed"]]
    totals = {
        "open": len(open_tasks),
        "done": len(tasks) - len(open_tasks),
        "today": sum(1 for t in open_tasks if t["due_date"] == now.isoformat()),
        "overdue": sum(1 for t in open_tasks if t["due_date"] and t["due_date"] < now.isoformat()),
    }

    # The last 7 days, oldest first, for the bar chart.
    week = [(now - timedelta(days=n), done_per_day[now - timedelta(days=n)]) for n in range(6, -1, -1)]
    week_max = max([count for _, count in week] + [1])  # +[1] so an empty week doesn't divide by 0

    per_list = []
    for item in user_lists():
        in_list = [t for t in tasks if t["list_id"] == item["id"]]
        done = sum(1 for t in in_list if t["completed"])
        per_list.append({"list": item, "total": len(in_list), "done": done})

    return render_template(
        "stats.html", totals=totals, current=current, best=best, week=week, week_max=week_max,
        per_list=per_list,
        member_since=g.user["created_at"][:10],
    )

