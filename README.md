# to_do_list_app

A to-do list web app built with **Python**, **Flask** and **SQLite**, made to practice CRUD, basic programming logic, forms and validation.

## Features

- **Accounts**: sign up, log in and log out. Each person sees and changes only their own tasks.
- **Create** tasks with a title, an optional description and an optional due date.
- **Edit** a task.
- **Complete** a task, or mark it as not done again.
- **Delete** a task, after a confirmation prompt.
- **Filter** the list with the tabs: All, Active, Due today, Overdue and Completed. Each tab shows how many tasks it holds.
- **Search** tasks by title and description.
- **Due date labels**: "Overdue" in red, "Due today", "Due tomorrow" or the date itself.
- **Validation**: a form with mistakes is shown again with a message under each field, and what you typed is kept.

## Setup (Windows, PowerShell)

Python 3.13 is installed at `%LOCALAPPDATA%\Programs\Python\Python313` but isn't on PATH, so typing `python` opens the Microsoft Store. Create the virtual environment from the full path once. After that, use the `.venv` copy.

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Run

```powershell
.venv\Scripts\flask --app todo run --debug
```

Then open http://127.0.0.1:5000. The database (`instance/todo.sqlite`) is created automatically on first run.

Open **Sign up** to create an account. To delete every task and account and start fresh, run `.venv\Scripts\flask --app todo init-db --reset`.

Tasks made before accounts were added have no owner, so they no longer show up. The app adds the `user_id` column to an old database automatically when it starts.

## Test

```powershell
.venv\Scripts\python -m pytest
```

## What each file teaches

| File | Topic |
|---|---|
| `todo/__init__.py` | The app factory: building the Flask app and its settings |
| `todo/schema.sql` | Designing tables: column types, `NOT NULL`, defaults, `UNIQUE`, and linking a task to its user |
| `todo/db.py` | Opening and closing a database connection per request; a custom `flask` command |
| `todo/tasks.py` | **CRUD**: `INSERT`, `SELECT`, `UPDATE` and `DELETE` with safe `?` placeholders. **Logic**: filtering, counting, sorting and due-date labels. Post/Redirect/Get |
| `todo/validation.py` | **Validation**: trimming input, required fields, length limits, date parsing, regular expressions, and rules that depend on other data |
| `todo/auth.py` | **Logins**: password hashing, the session cookie, `g.user`, and why logout is a POST |
| `todo/csrf.py` | Why every POST form carries a hidden token |
| `todo/templates/` | **Forms** with Jinja: showing errors per field, keeping typed values, template inheritance |
| `tests/` | Testing with pytest: plain function tests and fake web requests |

## Ideas to practice next

- Add a **priority** field (Low, Medium, High). You'll touch `schema.sql`, `validation.py`, `form.html`, `index.html` and the tests.
- Add a "Clear completed" button that deletes every finished task in one `DELETE ... WHERE completed = 1`.
- Sort by priority, or let the user choose the sort order.
- Add `novalidate` to the form in `form.html` to watch the server-side validation catch bad input on its own.
