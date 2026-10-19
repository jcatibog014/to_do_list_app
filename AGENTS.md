# AGENTS.md

This file guides AI coding agents (Claude Code, Codex, Cursor, Copilot and others) working in this repository.

## Overview

A to-do list web app in Python (Flask + SQLite, using the stdlib `sqlite3` with no ORM). It is a learning project for CRUD, programming logic, forms and validation. Keep the code readable for a learner: short comments that explain *why*, and no extra libraries such as WTForms or SQLAlchemy unless the owner asks for them.

Python 3.13 is at `%LOCALAPPDATA%\Programs\Python\Python313\python.exe` and is **not on PATH** (`python` opens the Microsoft Store alias). Use the virtual environment:

- Install: `.venv\Scripts\python -m pip install -r requirements.txt` (create `.venv` from the full Python path first if it's missing).
- Run: `.venv\Scripts\flask --app todo run --debug`, then open http://127.0.0.1:5000.
- Test: `.venv\Scripts\python -m pytest`.

## Architecture

- `todo/__init__.py` holds `create_app(test_config)`. Its config includes `DATABASE` (`instance/todo.sqlite`, which git ignores) and `TODAY`, a function returning today's date. Use `tasks.today()`, never `date.today()` directly, so tests can fix the date.
- `todo/db.py`: `get_db()` keeps one connection per request on `g`, with `row_factory = sqlite3.Row`. `init_db()` runs `schema.sql` on startup. The schema uses `CREATE TABLE IF NOT EXISTS`. Changing a column needs `flask --app todo init-db --reset` or an `ALTER TABLE`, like `add_user_id_column()`, which upgrades databases made before accounts existed.
- `todo/auth.py` is the `auth` blueprint: `/register`, `/login` and `/logout` (POST only). Passwords are stored with werkzeug's `generate_password_hash`. Logging in puts `user_id` in the session, and `load_logged_in_user()` sets `g.user` (a row, or `None`) before every request.
- `todo/tasks.py` is the `tasks` blueprint with every task route. Always pass SQL values as `?` placeholders.
  - `require_login()` sends logged-out visitors to `/login`. Every task query filters on `user_id = g.user["id"]`, and `get_task_or_404()` returns 404 for someone else's task.
  - Every POST action ends with `back_to_list()`, which keeps the `status`/`q` from `list_args()`. Templates get the same values as `keep`, and add them to links with `**keep`.
  - `index()` loads all tasks in display order with SQL. Search, `matches()` (filter tabs) and `due_badge()` then run in Python. Due dates are `YYYY-MM-DD` strings, so they compare correctly as text.
- `todo/validation.py`: `validate_task(form, today, existing_due_date)` and `validate_registration(form)` return `(data, errors)`. It must not import Flask. On errors, the views re-render `form.html` with HTTP 400 and keep the user's input.
  - To add a field, update `schema.sql`, `validate_task`, both SQL statements in `tasks.py` and `form.html`. Each field shows its error in `<p class="error" id="{name}-error">`.
- `todo/csrf.py`: every POST form must include `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`. Otherwise the request gets 400.
- Error pages (400, 404) render `error.html` through `error_page()` in `tasks.py`.
- Tests live in `tests/`.
  - The `conftest.py` fixtures are `client` (logged in as alice, user 1), `guest` (the same client, logged out), `other_user` (creates bob), `post` (sends the CSRF token), `add` (inserts directly, skipping validation, for alice unless `user_id=` is given) and `fetch` (reads a row).
  - Every test runs with today fixed to 2026-10-19.

## Conventions

- Styling: `todo/static/style.css`, with colors as CSS variables on `:root`, `color-mix(in srgb, …)`, light theme only, and a phone breakpoint at 520px.
- Keep comments teaching-oriented but brief. Add or update a test with every behavior change.
