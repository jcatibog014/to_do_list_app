"""Every task page and action: Create, Read, Update, Delete (CRUD), plus
quick add, lists, tags and reminders.

SQL rule used throughout: values from the user are always passed as ?
placeholders, never pasted into the SQL string with f-strings or +.
sqlite3 then treats them strictly as data, which prevents SQL injection.
"""
import sqlite3
from datetime import date, datetime, timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from .db import get_db
from .quickadd import parse_quick_add
from .recurrence import describe_repeat, next_due_after
from .validation import (
    DESCRIPTION_MAX,
    LIST_NAME_MAX,
    REMINDERS,
    TITLE_MAX,
    validate_list_name,
    validate_task,
)

bp = Blueprint("tasks", __name__)

# The filter tabs: value used in the URL (?status=...) -> label shown.
FILTERS = {
    "all": "All",
    "today": "Today",
    "active": "Active",
    "overdue": "Overdue",
    "completed": "Completed",
}


# Every page here needs someone logged in. Checking once for the whole
# blueprint means a new route can't forget the check.
@bp.before_request
def require_login():
    if g.user is None:
        return redirect(url_for("auth.login"))


# ---------- Helpers ----------

def today():
    return current_app.config["TODAY"]()


def get_task_or_404(task_id):
    # "AND user_id = ?" means someone else's task is "not found" too, so
    # nobody can view or change it by typing its id into the URL.
    task = get_db().execute(
        "SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, g.user["id"])
    ).fetchone()
    if task is None:
        abort(404, f"Task {task_id} doesn't exist. It may have been deleted.")
    return task


def get_list_or_404(list_id):
    found = get_db().execute(
        "SELECT * FROM lists WHERE id = ? AND user_id = ?", (list_id, g.user["id"])
    ).fetchone()
    if found is None:
        abort(404, f"List {list_id} doesn't exist. It may have been deleted.")
    return found


def user_lists():
    return get_db().execute(
        "SELECT * FROM lists WHERE user_id = ? ORDER BY name", (g.user["id"],)
    ).fetchall()


def check_list(data, errors):
    """Refuse a list_id that isn't one of the user's own lists."""
    if data["list_id"] is not None and data["list_id"] not in {l["id"] for l in user_lists()}:
        errors["list_id"] = "Choose a list from the menu."


def task_tags():
    """Map each of the user's task ids to its tag names, e.g. {3: ["home", "urgent"]}."""
    # JOIN pairs each task_tags row with its row in tags, to get the name.
    rows = get_db().execute(
        "SELECT task_tags.task_id, tags.name FROM task_tags"
        " JOIN tags ON tags.id = task_tags.tag_id"
        " WHERE tags.user_id = ? ORDER BY tags.name",
        (g.user["id"],),
    ).fetchall()
    tags = {}
    for row in rows:
        tags.setdefault(row["task_id"], []).append(row["name"])
    return tags


def save_tags(db, task_id, tags):
    """Replace a task's tags with `tags`, a list of names."""
    db.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
    for name in tags:
        # OR IGNORE: if the user already has this tag, the UNIQUE rule
        # stops a second copy, and sqlite3 carries on without an error.
        db.execute("INSERT OR IGNORE INTO tags (user_id, name) VALUES (?, ?)", (g.user["id"], name))
        tag = db.execute(
            "SELECT id FROM tags WHERE user_id = ? AND name = ?", (g.user["id"], name)
        ).fetchone()
        db.execute("INSERT INTO task_tags (task_id, tag_id) VALUES (?, ?)", (task_id, tag["id"]))


def insert_task(db, data):
    """Save a new task for the logged-in user and return its id. The caller commits."""
    cursor = db.execute(
        "INSERT INTO tasks (user_id, list_id, title, description, due_date, due_time, repeat, remind_before)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (g.user["id"], data["list_id"], data["title"], data["description"], data["due_date"],
         data["due_time"], data["repeat"], data["remind_before"]),
    )
    save_tags(db, cursor.lastrowid, data["tags"])
    return cursor.lastrowid


def matches(task, status, today):
    """True if `task` belongs under the filter tab `status`."""
    # Dates are 'YYYY-MM-DD' strings, so comparing them as text also
    # compares them as dates: '2026-01-31' < '2026-02-01'.
    due = task["due_date"]
    done = task["completed"]
    if status == "active":
        return not done
    if status == "completed":
        return bool(done)
    if status == "today":
        # What matters right now: due today, or already late.
        return not done and due is not None and due <= today.isoformat()
    if status == "overdue":
        return not done and due is not None and due < today.isoformat()
    return True  # "all"


def format_time(hhmm):
    """'17:05' -> '5:05 PM'."""
    hour, minute = (int(part) for part in hhmm.split(":"))
    return f"{hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}"


def due_badge(task, today):
    """The label and style for a task's due date, or None if it has none."""
    if not task["due_date"]:
        return None
    due = date.fromisoformat(task["due_date"])
    nice = f"{due:%b} {due.day}"  # e.g. "Oct 21"
    if due.year != today.year:
        nice += f", {due.year}"
    at = f", {format_time(task['due_time'])}" if task["due_time"] else ""
    if task["completed"]:
        return {"text": f"Due {nice}{at}", "kind": ""}

    days_left = (due - today).days
    if days_left < 0:
        return {"text": f"Overdue · {nice}{at}", "kind": "overdue"}
    if days_left == 0:
        return {"text": f"Due today{at}", "kind": "today"}
    if days_left == 1:
        return {"text": f"Due tomorrow{at}", "kind": "soon"}
    return {"text": f"Due {nice}{at}", "kind": ""}


def list_args():
    """What the user is looking at, to keep in links and redirects.

    For example {"status": "today", "list": "3", "tag": "home"}. "list" is
    a list's id, or "inbox" for tasks in no list.
    """
    args = {}
    status = request.values.get("status")
    if status in FILTERS and status != "all":
        args["status"] = status
    q = request.values.get("q", "").strip()
    if q:
        args["q"] = q
    shown_list = request.values.get("list", "")
    if shown_list == "inbox" or shown_list.isdigit():
        args["list"] = shown_list
    tag = request.values.get("tag", "").strip().lstrip("#").lower()
    if tag:
        args["tag"] = tag
    return args


def list_url(**changes):
    """The list page's URL with some of the current view changed.

    list_url(tag="home") keeps the tab, search and list but shows only
    #home. A value of None removes that part: list_url(q=None) clears the search.
    """
    args = {**list_args(), **changes}
    return url_for("tasks.index", **{key: value for key, value in args.items() if value is not None})


def back_to_list():
    """Redirect to the list, with the filter and search the user had.

    Redirecting after a POST (Post/Redirect/Get) means refreshing the page
    won't submit the form a second time.
    """
    return redirect(list_url())


@bp.app_context_processor
def template_values():
    # Every template can use `keep` to carry the current view in its links,
    # and list_url() to change part of it.
    return {"keep": list_args(), "list_url": list_url}


@bp.app_errorhandler(400)
@bp.app_errorhandler(404)
def error_page(e):
    return render_template("error.html", error=e), e.code


# ---------- Read ----------

@bp.route("/")
def index():
    return render_list()


def render_list(quick_text="", quick_error=None):
    """The list page. quick_add() uses it too, to show its error message."""
    args = list_args()
    status = args.get("status", "all")
    q = args.get("q", "")
    tag = args.get("tag")
    now = today()

    lists = user_lists()
    current_list = None
    # The SQL is built in pieces, but only from fixed text. The values
    # still go in separately, as ? placeholders.
    sql = "SELECT * FROM tasks WHERE user_id = ?"
    params = [g.user["id"]]
    if args.get("list") == "inbox":
        sql += " AND list_id IS NULL"
    elif "list" in args:
        current_list = get_list_or_404(int(args["list"]))
        sql += " AND list_id = ?"
        params.append(current_list["id"])
    # Display order: unfinished first, then by due date and time (tasks
    # without one last), then newest first.
    sql += (" ORDER BY completed, due_date IS NULL, due_date, due_time IS NULL, due_time,"
            " created_at DESC, id DESC")
    rows = get_db().execute(sql, params).fetchall()

    tags = task_tags()
    tasks = [dict(t, tags=tags.get(t["id"], [])) for t in rows]

    # Tag and search first, so the counts on the tabs match them.
    # casefold() makes the search ignore upper/lower case.
    if tag:
        tasks = [t for t in tasks if tag in t["tags"]]
    if q:
        needle = q.casefold()
        tasks = [
            t for t in tasks
            if needle in t["title"].casefold()
            or needle in t["description"].casefold()
            or any(needle in f"#{name}" for name in t["tags"])
        ]

    counts = {key: sum(1 for t in tasks if matches(t, key, now)) for key in FILTERS}
    list_names = {l["id"]: l["name"] for l in lists}
    shown = [
        dict(
            t,
            badge=due_badge(t, now),
            repeat_text=describe_repeat(t["repeat"]) if t["repeat"] else None,
            list_name=list_names.get(t["list_id"]),
        )
        for t in tasks if matches(t, status, now)
    ]

    if current_list:
        heading = current_list["name"]
    elif args.get("list") == "inbox":
        heading = "Inbox"
    else:
        heading = "My tasks"

    html = render_template(
        "index.html", tasks=shown, counts=counts, filters=FILTERS, status=status, q=q,
        tag=tag, lists=lists, current_list=current_list, shown_list=args.get("list"),
        heading=heading, quick_text=quick_text, quick_error=quick_error,
        list_name_max=LIST_NAME_MAX,
    )
    return html, 400 if quick_error else 200


# ---------- Create ----------

@bp.post("/tasks/quick")
def quick_add():
    """Add a task from one line of text, like "pay rent friday 5pm #home"."""
    text = request.form.get("text", "").strip()
    parsed = parse_quick_add(text, today())
    shown_list = list_args().get("list", "")

    # Turn the parts into form fields, so validate_task() checks them
    # exactly like it checks the full form.
    form = {
        "title": parsed["title"],
        "due_date": parsed["due_date"] or "",
        "due_time": parsed["due_time"] or "",
        "repeat": describe_repeat(parsed["repeat"]) if parsed["repeat"] else "",
        # Typing a time also sets a reminder for that time.
        "remind_before": "0" if parsed["due_time"] else "",
        "tags": " ".join(parsed["tags"]),
        # Add to the list on screen. The Inbox and "All" both mean no list.
        "list_id": shown_list if shown_list.isdigit() else "",
    }
    data, errors = validate_task(form, today())
    check_list(data, errors)
    if errors:
        if "title" in errors and not parsed["title"]:
            errors["title"] = "Type what the task is, like “pay rent friday 5pm”."
        return render_list(quick_text=text, quick_error=" ".join(errors.values()))

    db = get_db()
    insert_task(db, data)
    db.commit()
    message = f"Added “{data['title']}”."
    badge = due_badge({**data, "completed": 0}, today())
    if badge:
        message += f" {badge['text']}."
    if data["repeat"]:
        message += f" Repeats {describe_repeat(data['repeat'])}."
    flash(message)
    return back_to_list()


@bp.route("/tasks/new", methods=["GET", "POST"])
def create():
    # A new task starts in the list on screen.
    shown_list = list_args().get("list", "")
    form, errors = {"list_id": shown_list if shown_list.isdigit() else ""}, {}
    if request.method == "POST":
        form = request.form
        data, errors = validate_task(form, today())
        check_list(data, errors)
        if not errors:
            db = get_db()
            insert_task(db, data)
            db.commit()
            flash(f"Added “{data['title']}”.")
            return back_to_list()

    # On errors, show the form again with what the user typed, and answer
    # with 400 Bad Request instead of 200 OK.
    return render_form(form, errors, task=None)


# ---------- Update ----------

def task_form(task):
    """A saved task as text fields, to fill in the edit form."""
    return {
        **dict(task),
        "due_date": task["due_date"] or "",
        "due_time": task["due_time"] or "",
        "repeat": describe_repeat(task["repeat"]) if task["repeat"] else "",
        "remind_before": "" if task["remind_before"] is None else str(task["remind_before"]),
        "tags": ", ".join(task_tags().get(task["id"], [])),
        "list_id": "" if task["list_id"] is None else str(task["list_id"]),
    }


@bp.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
def edit(task_id):
    task = get_task_or_404(task_id)
    form, errors = task_form(task), {}
    if request.method == "POST":
        form = request.form
        data, errors = validate_task(form, today(), existing_due_date=task["due_date"])
        check_list(data, errors)
        if not errors:
            db = get_db()
            db.execute(
                "UPDATE tasks SET list_id = ?, title = ?, description = ?, due_date = ?,"
                " due_time = ?, repeat = ?, remind_before = ? WHERE id = ?",
                (data["list_id"], data["title"], data["description"], data["due_date"],
                 data["due_time"], data["repeat"], data["remind_before"], task_id),
            )
            save_tags(db, task_id, data["tags"])
            db.commit()
            flash(f"Saved “{data['title']}”.")
            return back_to_list()

    return render_form(form, errors, task=task)


@bp.post("/tasks/<int:task_id>/toggle")
def toggle(task_id):
    task = get_task_or_404(task_id)
    db = get_db()
    if task["completed"]:
        db.execute("UPDATE tasks SET completed = 0, completed_at = NULL WHERE id = ?", (task_id,))
        flash(f"Marked “{task['title']}” as not done.")
        db.commit()
        return back_to_list()

    # The done task also gives up its repeat rule. A new copy takes over
    # the rule, so un-ticking and re-ticking this one can't make a second copy.
    db.execute(
        "UPDATE tasks SET completed = 1, completed_at = datetime('now', 'localtime'), repeat = NULL"
        " WHERE id = ?",
        (task_id,),
    )
    message = f"Completed “{task['title']}”."
    if task["repeat"] and task["due_date"]:
        next_date = next_due_after(task["repeat"], date.fromisoformat(task["due_date"]), today())
        copy = {
            **dict(task),
            "due_date": next_date.isoformat(),
            "tags": task_tags().get(task_id, []),
        }
        insert_task(db, copy)
        message += f" Next one: {due_badge({**copy, 'completed': 0}, today())['text']}."
    db.commit()
    flash(message)
    return back_to_list()


# ---------- Delete ----------

@bp.post("/tasks/<int:task_id>/delete")
def delete(task_id):
    task = get_task_or_404(task_id)
    db = get_db()
    # Remove the task's tag links first, so none point to a missing task.
    db.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    flash(f"Deleted “{task['title']}”.")
    return back_to_list()


def render_form(form, errors, task):
    html = render_template(
        "form.html",
        form=form,
        errors=errors,
        task=task,
        today=today().isoformat(),
        title_max=TITLE_MAX,
        description_max=DESCRIPTION_MAX,
        lists=user_lists(),
        reminders=REMINDERS,
    )
    return html, 400 if errors else 200


# ---------- Lists ----------

@bp.post("/lists/new")
def create_list():
    name, error = validate_list_name(request.form)
    if error is None:
        db = get_db()
        try:
            cursor = db.execute(
                "INSERT INTO lists (user_id, name) VALUES (?, ?)", (g.user["id"], name)
            )
            db.commit()
        except sqlite3.IntegrityError:
            # The UNIQUE (user_id, name) rule in schema.sql refused it.
            error = f"You already have a list called “{name}”."
        else:
            flash(f"Made the list “{name}”.")
            return redirect(url_for("tasks.index", list=cursor.lastrowid))
    flash(error, "error")
    return back_to_list()


@bp.post("/lists/<int:list_id>/delete")
def delete_list(list_id):
    found = get_list_or_404(list_id)
    db = get_db()
    # Keep the tasks: move them to the Inbox, so none point to a missing list.
    db.execute("UPDATE tasks SET list_id = NULL WHERE list_id = ?", (list_id,))
    db.execute("DELETE FROM lists WHERE id = ?", (list_id,))
    db.commit()
    flash(f"Deleted the list “{found['name']}”. Its tasks are in the Inbox now.")
    return redirect(url_for("tasks.index"))


# ---------- Reminders ----------

@bp.get("/reminders")
def reminders():
    """The user's reminders as JSON. static/reminders.js asks for this every half minute."""
    rows = get_db().execute(
        "SELECT * FROM tasks WHERE user_id = ? AND completed = 0"
        " AND remind_before IS NOT NULL AND due_date IS NOT NULL AND due_time IS NOT NULL",
        (g.user["id"],),
    ).fetchall()
    result = []
    for row in rows:
        due = datetime.fromisoformat(f"{row['due_date']}T{row['due_time']}")
        remind_at = due - timedelta(minutes=row["remind_before"])
        result.append({
            "id": row["id"],
            "title": row["title"],
            # Like '2026-10-23T16:50', with no time zone, so the browser
            # reads it as its own local time.
            "at": remind_at.isoformat(timespec="minutes"),
            "when": due_badge(row, today())["text"],
        })
    # Flask sends a returned dict as JSON.
    return {"reminders": result}
