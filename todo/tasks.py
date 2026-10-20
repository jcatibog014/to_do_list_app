"""Every task page and action: Create, Read, Update, Delete (CRUD), plus
quick add, subtasks, the board, focus mode, undo and reminders.

Lists have their own file (lists.py), and so do the calendar and stats
pages (pages.py). Both use the helpers at the top of this file.

SQL rule used throughout: values from the user are always passed as ?
placeholders, never pasted into the SQL string with f-strings or +.
sqlite3 then treats them strictly as data, which prevents SQL injection.
"""
import json
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
    session,
    url_for,
)

from .auth import require_login
from .db import get_db
from .quickadd import parse_quick_add
from .recurrence import describe_repeat, next_due_after
from .validation import (
    DESCRIPTION_MAX,
    EMOJI_CHOICES,
    LIST_COLORS,
    REMINDERS,
    SUBTASK_MAX,
    SUBTASKS_MAX,
    TITLE_MAX,
    capitalize_first,
    validate_subtask,
    validate_task,
)

bp = Blueprint("tasks", __name__)
# Every page here needs someone logged in.
bp.before_request(require_login)

# The filter tabs: value used in the URL (?status=...) -> label shown.
FILTERS = {
    "all": "All",
    "today": "Today",
    "active": "Active",
    "overdue": "Overdue",
    "completed": "Completed",
}

# How the tasks are laid out: a grid of cards, a compact list, or a board.
VIEWS = {"cards": "Grid", "list": "List", "board": "Board"}

# The board's columns. "done" is the completed column, and "doing" is the
# tasks.doing column.
BOARD_COLUMNS = {"todo": "To Do", "doing": "Doing", "done": "Done"}


# ---------- Helpers ----------

def today():
    return current_app.config["TODAY"]()


def is_fetch():
    """True when JavaScript sent the request with fetch(), not a normal form.

    static/app.js and focus.js add this header, so the server can answer
    with nothing instead of a whole page.
    """
    return request.headers.get("X-Requested-With") == "fetch"


def notify(message, category="message"):
    """flash() a message for the next page.

    fetch() calls show their own feedback on the page, so they get none.
    Category "undo" shows an Undo button, and "error" shows in red.
    """
    if not is_fetch():
        flash(message, category)


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


def get_subtask_or_404(subtask_id):
    # A subtask has no user_id of its own, so JOIN to its task to check the owner.
    step = get_db().execute(
        "SELECT subtasks.* FROM subtasks JOIN tasks ON tasks.id = subtasks.task_id"
        " WHERE subtasks.id = ? AND tasks.user_id = ?",
        (subtask_id, g.user["id"]),
    ).fetchone()
    if step is None:
        abort(404, f"Subtask {subtask_id} doesn't exist. It may have been deleted.")
    return step


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


def task_subtasks():
    """Map each of the user's task ids to its subtask rows, oldest first."""
    rows = get_db().execute(
        "SELECT subtasks.* FROM subtasks JOIN tasks ON tasks.id = subtasks.task_id"
        " WHERE tasks.user_id = ? ORDER BY subtasks.id",
        (g.user["id"],),
    ).fetchall()
    subtasks = {}
    for row in rows:
        subtasks.setdefault(row["task_id"], []).append(row)
    return subtasks


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
    """Save a new task for the logged-in user and return its id. The caller commits.

    data["subtasks"], if there, is a list of subtask titles to add.
    """
    cursor = db.execute(
        "INSERT INTO tasks (user_id, list_id, title, description, due_date, due_time, repeat,"
        " remind_before, priority, emoji, doing) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (g.user["id"], data["list_id"], data["title"], data["description"], data["due_date"],
         data["due_time"], data["repeat"], data["remind_before"], data["priority"],
         data["emoji"], data.get("doing", 0)),
    )
    task_id = cursor.lastrowid
    save_tags(db, task_id, data["tags"])
    for title in data.get("subtasks", []):
        db.execute("INSERT INTO subtasks (task_id, title) VALUES (?, ?)", (task_id, title))
    return task_id


def delete_task_rows(db, task_id):
    """Delete a task and the rows that point to it. The caller commits."""
    # Children first, so no tag link or subtask is left pointing to nothing.
    db.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
    db.execute("DELETE FROM subtasks WHERE task_id = ?", (task_id,))
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def save_undo(db, action):
    """Remember `action` (a dict) as the one thing the user can undo.

    json.dumps() turns the dict into text for the database, and
    json.loads() in undo() turns it back.
    """
    db.execute(
        "INSERT OR REPLACE INTO undo (user_id, data) VALUES (?, ?)",
        (g.user["id"], json.dumps(action)),
    )


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


def tag_color(name):
    """A color for a tag, worked out from its letters.

    The same name always gets the same color, so #home looks the same
    everywhere, without saving a color for every tag.
    """
    return LIST_COLORS[sum(ord(letter) for letter in name) % len(LIST_COLORS)]


def decorate(rows, now):
    """Turn task rows into dicts with everything the templates show.

    Adds the tags, the due-date badge, the repeat in words, the list's name
    and color, and the subtasks with how many are done.
    """
    lists_by_id = {l["id"]: l for l in user_lists()}
    tags = task_tags()
    subtasks = task_subtasks()
    tasks = []
    for row in rows:
        in_list = lists_by_id.get(row["list_id"])
        steps = subtasks.get(row["id"], [])
        steps_done = sum(1 for step in steps if step["done"])
        tasks.append(dict(
            row,
            tags=tags.get(row["id"], []),
            badge=due_badge(row, now),
            repeat_text=describe_repeat(row["repeat"]) if row["repeat"] else None,
            list_name=in_list["name"] if in_list else None,
            # Each card takes its list's color. Inbox tasks are gray.
            color=in_list["color"] if in_list else "slate",
            subtasks=steps,
            subtasks_done=steps_done,
            # A percentage for the progress ring, or None with no subtasks.
            progress=round(100 * steps_done / len(steps)) if steps else None,
        ))
    return tasks


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


def go_back(task_id=None):
    """Where to go after an action: back to the page the form was on.

    Forms on other pages say where they are with a hidden "next" field.
    fetch() calls get an empty "204 No Content" answer instead of a page.
    """
    if is_fetch():
        return "", 204
    where = request.values.get("next")
    if where == "focus":
        return redirect(url_for("tasks.focus"))
    if where == "edit" and task_id:
        return redirect(url_for("tasks.edit", task_id=task_id, **list_args()))
    if where == "calendar":
        # url_for() leaves out values that are None.
        return redirect(url_for("pages.calendar", month=request.values.get("month"),
                                day=request.values.get("day")))
    if where == "lists":
        return redirect(url_for("lists.index"))
    return back_to_list()


# In templates: {{ task.title|capfirst }}. Older tasks may have been saved
# before titles were capitalized, so the pages capitalize them too.
bp.add_app_template_filter(capitalize_first, "capfirst")


@bp.app_context_processor
def template_values():
    # Every template can use `keep` to carry the current view in its links,
    # list_url() to change part of it, and tag_color() for tag chips.
    return {"keep": list_args(), "list_url": list_url, "tag_color": tag_color}


@bp.app_errorhandler(400)
@bp.app_errorhandler(404)
def error_page(e):
    return render_template("error.html", error=e), e.code


# ---------- Read ----------

@bp.route("/")
def index():
    return render_list()


def render_list(quick_text="", quick_error=None):
    """The home page. quick_add() uses it too, to show its error message."""
    args = list_args()
    status = args.get("status", "all")
    q = args.get("q", "")
    tag = args.get("tag")
    now = today()

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
    tasks = decorate(get_db().execute(sql, params).fetchall(), now)

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
    shown = [t for t in tasks if matches(t, status, now)]

    # The day's progress bar: of the tasks due today, how many are done.
    due_today = [t for t in tasks if t["due_date"] == now.isoformat()]
    day_done = sum(1 for t in due_today if t["completed"])

    # The board sorts the same tasks into its three columns.
    board = {key: [] for key in BOARD_COLUMNS}
    for t in shown:
        column = "done" if t["completed"] else "doing" if t["doing"] else "todo"
        board[column].append(t)

    if current_list:
        heading = capitalize_first(current_list["name"])
    elif args.get("list") == "inbox":
        heading = "Inbox"
    else:
        heading = "My Tasks"

    html = render_template(
        "index.html", tasks=shown, counts=counts, filters=FILTERS, status=status, q=q,
        tag=tag, lists=user_lists(), current_list=current_list, shown_list=args.get("list"),
        heading=heading, quick_text=quick_text, quick_error=quick_error,
        today_text=f"{now:%A}, {now:%B} {now.day}",  # e.g. "Monday, October 19"
        day_total=len(due_today), day_done=day_done,
        views=VIEWS, view=session.get("view", "cards"),
        board=board, board_columns=BOARD_COLUMNS,
    )
    return html, 400 if quick_error else 200


@bp.post("/view")
def set_view():
    """Switch between the grid, the list and the board.

    The choice is kept in the session, so it lasts until you log out.
    """
    view = request.form.get("view")
    if view in VIEWS:
        session["view"] = view
    return back_to_list()


@bp.get("/focus")
def focus():
    """Focus mode: one unfinished task at a time, the most important first.

    ?skip=4,7 lists the tasks put off with "Later". They go to the back of
    the stack, in the order they were skipped. (With JavaScript on,
    focus.js does this in the page instead.)
    """
    skip = [int(n) for n in request.args.get("skip", "").split(",") if n.isdigit()]
    rows = get_db().execute(
        "SELECT * FROM tasks WHERE user_id = ? AND completed = 0"
        " ORDER BY priority DESC, due_date IS NULL, due_date, due_time IS NULL, due_time, id",
        (g.user["id"],),
    ).fetchall()
    tasks = decorate(rows, today())
    # sort() keeps the order of equal items, so tasks not skipped (key 0)
    # stay in priority order at the front.
    tasks.sort(key=lambda t: skip.index(t["id"]) + 1 if t["id"] in skip else 0)
    later = ",".join(str(n) for n in skip + [tasks[0]["id"]]) if tasks else ""
    return render_template("focus.html", tasks=tasks, later=later)


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
        "priority": "1" if parsed["priority"] else "",
        "emoji": parsed["emoji"] or "",
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
    notify(message)
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
            notify(f"Added “{data['title']}”.")
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
        "emoji": task["emoji"] or "",
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
                " due_time = ?, repeat = ?, remind_before = ?, priority = ?, emoji = ? WHERE id = ?",
                (data["list_id"], data["title"], data["description"], data["due_date"],
                 data["due_time"], data["repeat"], data["remind_before"], data["priority"],
                 data["emoji"], task_id),
            )
            save_tags(db, task_id, data["tags"])
            db.commit()
            notify(f"Saved “{data['title']}”.")
            return back_to_list()

    return render_form(form, errors, task=task)


def complete_task(db, task):
    """Mark a task done, and make the next copy if it repeats.

    Returns the message to show. The caller commits.
    """
    # The done task also gives up its repeat rule. A new copy takes over
    # the rule, so un-ticking and re-ticking this one can't make a second copy.
    db.execute(
        "UPDATE tasks SET completed = 1, completed_at = datetime('now', 'localtime'),"
        " repeat = NULL, doing = 0 WHERE id = ?",
        (task["id"],),
    )
    message = f"Completed “{capitalize_first(task['title'])}”."
    copy_id = None
    if task["repeat"] and task["due_date"]:
        next_date = next_due_after(task["repeat"], date.fromisoformat(task["due_date"]), today())
        copy = {
            **dict(task),
            "due_date": next_date.isoformat(),
            "doing": 0,
            "tags": task_tags().get(task["id"], []),
            # The copy gets the same checklist, with nothing ticked.
            "subtasks": [step["title"] for step in task_subtasks().get(task["id"], [])],
        }
        copy_id = insert_task(db, copy)
        message += f" Next one: {due_badge({**copy, 'completed': 0}, today())['text']}."
    save_undo(db, {"action": "complete", "task_id": task["id"], "repeat": task["repeat"],
                   "doing": task["doing"], "copy_id": copy_id})
    return message


@bp.post("/tasks/<int:task_id>/toggle")
def toggle(task_id):
    task = get_task_or_404(task_id)
    db = get_db()
    if task["completed"]:
        db.execute("UPDATE tasks SET completed = 0, completed_at = NULL WHERE id = ?", (task_id,))
        notify(f"Marked “{capitalize_first(task['title'])}” as not done.")
    else:
        notify(complete_task(db, task), "undo")
    db.commit()
    return go_back()


@bp.post("/tasks/<int:task_id>/status")
def set_status(task_id):
    """Move a task to one of the board's columns: todo, doing or done."""
    task = get_task_or_404(task_id)
    status = request.form.get("status")
    if status not in BOARD_COLUMNS:
        abort(400, "That column doesn't exist.")
    db = get_db()
    if status == "done":
        if not task["completed"]:
            notify(complete_task(db, task), "undo")
    else:
        db.execute(
            "UPDATE tasks SET completed = 0, completed_at = NULL, doing = ? WHERE id = ?",
            (1 if status == "doing" else 0, task_id),
        )
        notify(f"Moved “{capitalize_first(task['title'])}” to {BOARD_COLUMNS[status]}.")
    db.commit()
    return go_back()


@bp.post("/tasks/<int:task_id>/tomorrow")
def tomorrow(task_id):
    """Put a task off until tomorrow, at the same time if it has one."""
    task = get_task_or_404(task_id)
    db = get_db()
    db.execute("UPDATE tasks SET due_date = ? WHERE id = ?",
               ((today() + timedelta(days=1)).isoformat(), task_id))
    db.commit()
    notify(f"Moved “{capitalize_first(task['title'])}” to tomorrow.")
    return go_back()


@bp.post("/tasks/<int:task_id>/priority")
def toggle_priority(task_id):
    task = get_task_or_404(task_id)
    db = get_db()
    db.execute("UPDATE tasks SET priority = ? WHERE id = ?", (0 if task["priority"] else 1, task_id))
    db.commit()
    notify(f"“{capitalize_first(task['title'])}” is {'normal' if task['priority'] else 'high'} priority now.")
    return go_back()


@bp.post("/tasks/<int:task_id>/move")
def move(task_id):
    """Move a task to another list, which also changes its card's color."""
    task = get_task_or_404(task_id)
    text = request.form.get("list_id", "")
    if text and not text.isdigit():
        abort(400, "Choose a list from the menu.")
    data, errors = {"list_id": int(text) if text else None}, {}
    check_list(data, errors)
    if errors:
        abort(400, errors["list_id"])
    db = get_db()
    db.execute("UPDATE tasks SET list_id = ? WHERE id = ?", (data["list_id"], task_id))
    db.commit()
    name = get_list_or_404(data["list_id"])["name"] if data["list_id"] else "Inbox"
    notify(f"Moved “{capitalize_first(task['title'])}” to {name}.")
    return go_back()


# ---------- Subtasks ----------

@bp.post("/tasks/<int:task_id>/subtasks")
def add_subtask(task_id):
    task = get_task_or_404(task_id)
    title, error = validate_subtask(request.form)
    if error is None and len(task_subtasks().get(task_id, [])) >= SUBTASKS_MAX:
        error = f"A task can have {SUBTASKS_MAX} subtasks at most."
    if error:
        notify(error, "error")
    else:
        db = get_db()
        db.execute("INSERT INTO subtasks (task_id, title) VALUES (?, ?)", (task_id, title))
        db.commit()
        notify(f"Added “{title}” to “{capitalize_first(task['title'])}”.")
    return go_back(task_id)


@bp.post("/subtasks/<int:subtask_id>/toggle")
def toggle_subtask(subtask_id):
    step = get_subtask_or_404(subtask_id)
    db = get_db()
    db.execute("UPDATE subtasks SET done = ? WHERE id = ?", (0 if step["done"] else 1, subtask_id))
    db.commit()
    # No message: the tick on the checkbox shows what happened.
    return go_back(step["task_id"])


@bp.post("/subtasks/<int:subtask_id>/delete")
def delete_subtask(subtask_id):
    step = get_subtask_or_404(subtask_id)
    db = get_db()
    db.execute("DELETE FROM subtasks WHERE id = ?", (subtask_id,))
    db.commit()
    notify(f"Removed “{capitalize_first(step['title'])}”.")
    return go_back(step["task_id"])


# ---------- Delete and undo ----------

@bp.post("/tasks/<int:task_id>/delete")
def delete(task_id):
    task = get_task_or_404(task_id)
    db = get_db()
    # Keep a copy of everything, so undo() can put it back.
    save_undo(db, {
        "action": "delete",
        "task": dict(task),
        "tags": task_tags().get(task_id, []),
        "subtasks": [dict(step) for step in task_subtasks().get(task_id, [])],
    })
    delete_task_rows(db, task_id)
    db.commit()
    notify(f"Deleted “{capitalize_first(task['title'])}”.", "undo")
    return go_back()


@bp.post("/undo")
def undo():
    """Take back the last completed or deleted task."""
    db = get_db()
    row = db.execute("SELECT data FROM undo WHERE user_id = ?", (g.user["id"],)).fetchone()
    if row is None:
        notify("There's nothing to undo.", "error")
        return go_back()
    action = json.loads(row["data"])
    db.execute("DELETE FROM undo WHERE user_id = ?", (g.user["id"],))

    if action["action"] == "complete":
        db.execute(
            "UPDATE tasks SET completed = 0, completed_at = NULL, repeat = ?, doing = ?"
            " WHERE id = ? AND user_id = ?",
            (action["repeat"], action["doing"], action["task_id"], g.user["id"]),
        )
        # Remove the next copy that completing made, if it's still there.
        copy = db.execute("SELECT id FROM tasks WHERE id = ? AND user_id = ?",
                          (action["copy_id"], g.user["id"])).fetchone()
        if copy:
            delete_task_rows(db, copy["id"])
        message = "Undone. The task is back on your list."
    else:
        task = action["task"]
        # Only real column names go into the SQL. They come from our own
        # saved copy, but checking them against the table costs nothing.
        real = {r["name"] for r in db.execute("PRAGMA table_info(tasks)")}
        columns = [name for name in task if name in real]
        db.execute(
            f"INSERT INTO tasks ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            [task[name] for name in columns],
        )
        save_tags(db, task["id"], action["tags"])
        for step in action["subtasks"]:
            db.execute("INSERT INTO subtasks (task_id, title, done) VALUES (?, ?, ?)",
                       (task["id"], step["title"], step["done"]))
        message = f"Brought back “{capitalize_first(task['title'])}”."
    db.commit()
    notify(message)
    return go_back()


def render_form(form, errors, task):
    html = render_template(
        "form.html",
        form=form,
        errors=errors,
        task=task,
        today=today().isoformat(),
        title_max=TITLE_MAX,
        description_max=DESCRIPTION_MAX,
        subtask_max=SUBTASK_MAX,
        lists=user_lists(),
        reminders=REMINDERS,
        emoji_choices=EMOJI_CHOICES,
        subtasks=task_subtasks().get(task["id"], []) if task else [],
    )
    return html, 400 if errors else 200


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
