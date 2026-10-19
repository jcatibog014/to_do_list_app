"""Every task page and action: Create, Read, Update, Delete (CRUD).

SQL rule used throughout: values from the user are always passed as ?
placeholders, never pasted into the SQL string with f-strings or +.
sqlite3 then treats them strictly as data, which prevents SQL injection.
"""
from datetime import date

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
from .validation import DESCRIPTION_MAX, TITLE_MAX, validate_task

bp = Blueprint("tasks", __name__)

# The filter tabs: value used in the URL (?status=...) -> label shown.
FILTERS = {
    "all": "All",
    "active": "Active",
    "today": "Due today",
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
        return not done and due == today.isoformat()
    if status == "overdue":
        return not done and due is not None and due < today.isoformat()
    return True  # "all"


def due_badge(task, today):
    """The label and style for a task's due date, or None if it has none."""
    if not task["due_date"]:
        return None
    due = date.fromisoformat(task["due_date"])
    nice = f"{due:%b} {due.day}"  # e.g. "Oct 21"
    if due.year != today.year:
        nice += f", {due.year}"
    if task["completed"]:
        return {"text": f"Due {nice}", "kind": ""}

    days_left = (due - today).days
    if days_left < 0:
        return {"text": f"Overdue · {nice}", "kind": "overdue"}
    if days_left == 0:
        return {"text": "Due today", "kind": "today"}
    if days_left == 1:
        return {"text": "Due tomorrow", "kind": "soon"}
    return {"text": f"Due {nice}", "kind": ""}


def list_args():
    """The filter and search to keep in links and redirects, e.g. {"status": "active"}."""
    args = {}
    status = request.values.get("status")
    if status in FILTERS and status != "all":
        args["status"] = status
    q = request.values.get("q", "").strip()
    if q:
        args["q"] = q
    return args


def back_to_list():
    """Redirect to the list, with the filter and search the user had.

    Redirecting after a POST (Post/Redirect/Get) means refreshing the page
    won't submit the form a second time.
    """
    return redirect(url_for("tasks.index", **list_args()))


@bp.app_context_processor
def template_values():
    # Every template can use `keep` to carry the current filter in its links.
    return {"keep": list_args()}


@bp.app_errorhandler(400)
@bp.app_errorhandler(404)
def error_page(e):
    return render_template("error.html", error=e), e.code


# ---------- Read ----------

@bp.route("/")
def index():
    status = request.args.get("status", "all")
    if status not in FILTERS:
        status = "all"
    q = request.args.get("q", "").strip()
    now = today()

    # One query loads the user's tasks, already in display order: unfinished
    # first, then by due date (tasks without one last), then newest first.
    rows = get_db().execute(
        "SELECT * FROM tasks WHERE user_id = ?"
        " ORDER BY completed, due_date IS NULL, due_date, created_at DESC, id DESC",
        (g.user["id"],),
    ).fetchall()

    # Search first, so the counts on the tabs match the search.
    # casefold() makes the search ignore upper/lower case.
    if q:
        needle = q.casefold()
        rows = [
            t for t in rows
            if needle in t["title"].casefold() or needle in t["description"].casefold()
        ]

    counts = {key: sum(1 for t in rows if matches(t, key, now)) for key in FILTERS}
    tasks = [dict(t, badge=due_badge(t, now)) for t in rows if matches(t, status, now)]

    return render_template(
        "index.html", tasks=tasks, counts=counts, filters=FILTERS, status=status, q=q
    )


# ---------- Create ----------

@bp.route("/tasks/new", methods=["GET", "POST"])
def create():
    form, errors = {}, {}
    if request.method == "POST":
        form = request.form
        data, errors = validate_task(form, today())
        if not errors:
            db = get_db()
            db.execute(
                "INSERT INTO tasks (user_id, title, description, due_date) VALUES (?, ?, ?, ?)",
                (g.user["id"], data["title"], data["description"], data["due_date"]),
            )
            db.commit()
            flash(f"Added “{data['title']}”.")
            return back_to_list()

    # On errors, show the form again with what the user typed, and answer
    # with 400 Bad Request instead of 200 OK.
    return render_form(form, errors, task=None)


# ---------- Update ----------

@bp.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
def edit(task_id):
    task = get_task_or_404(task_id)
    form, errors = dict(task), {}
    if request.method == "POST":
        form = request.form
        data, errors = validate_task(form, today(), existing_due_date=task["due_date"])
        if not errors:
            db = get_db()
            db.execute(
                "UPDATE tasks SET title = ?, description = ?, due_date = ? WHERE id = ?",
                (data["title"], data["description"], data["due_date"], task_id),
            )
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
    else:
        db.execute(
            "UPDATE tasks SET completed = 1, completed_at = datetime('now', 'localtime') WHERE id = ?",
            (task_id,),
        )
        flash(f"Completed “{task['title']}”.")
    db.commit()
    return back_to_list()


# ---------- Delete ----------

@bp.post("/tasks/<int:task_id>/delete")
def delete(task_id):
    task = get_task_or_404(task_id)
    db = get_db()
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
    )
    return html, 400 if errors else 200
