# AGENTS.md

This file guides AI coding agents (Claude Code, Codex, Cursor, Copilot and others) working in this repository.

## Overview

Later Gator, a to-do list web app in Python (Flask + SQLite, using the stdlib `sqlite3` with no ORM). It is a learning project for CRUD, programming logic, forms and validation. Keep the code readable for a learner: short comments that explain *why*, and no extra libraries such as WTForms or SQLAlchemy unless the owner asks for them.

Python 3.13 is at `%LOCALAPPDATA%\Programs\Python\Python313\python.exe` and is **not on PATH** (`python` opens the Microsoft Store alias). Use the virtual environment:

- Install: `.venv\Scripts\python -m pip install -r requirements.txt` (create `.venv` from the full Python path first if it's missing).
- Run: `.venv\Scripts\flask --app todo run --debug`, then open http://127.0.0.1:5000.
- Test: `.venv\Scripts\python -m pytest`.

## Architecture

- `todo/__init__.py` holds `create_app(test_config)`. Its config includes `DATABASE` (`instance/todo.sqlite`, which git ignores) and `TODAY`, a function returning today's date. Use `tasks.today()`, never `date.today()` directly, so tests can fix the date.
- `todo/db.py`: `get_db()` keeps one connection per request on `g`, with `row_factory = sqlite3.Row`. `init_db()` runs `schema.sql` on startup. The schema uses `CREATE TABLE IF NOT EXISTS`. A new column in an existing table must also go in `NEW_COLUMNS` (by table), so `add_missing_columns()` adds it to older databases with `ALTER TABLE` (new tables are created by `schema.sql` on their own).
- `todo/auth.py` is the `auth` blueprint: `/register`, `/login` and `/logout` (POST only). Passwords are stored with werkzeug's `generate_password_hash`. Logging in puts `user_id` in the session, and `load_logged_in_user()` sets `g.user` (a row, or `None`) before every request.
- Blueprints: `tasks` (`todo/tasks.py`: every task route, plus the shared helpers), `lists` (`todo/lists.py`: the Lists page, create, rename, color, delete) `pages` (`todo/pages.py`: Calendar and Stats) and `profile` (`todo/profile.py`: picture, display name, username, password, and theme at `POST /profile/theme`). Each one calls `bp.before_request(require_login)` from `auth.py`. Always pass SQL values as `?` placeholders.
- `todo/tasks.py`:
  - Logged-out visitors are sent to `/login`. Every task query filters on `user_id = g.user["id"]`, and `get_task_or_404()` returns 404 for someone else's task.
  - `get_list_or_404()` does the same for lists, and `check_list()` refuses a `list_id` that belongs to someone else.
  - `list_args()` is the current view: `status`, `q`, `list` (an id or `"inbox"`) and `tag`. POST actions end with `go_back()`: a hidden `next` field (`focus`, `edit`, `calendar` or `lists`, made by `ui.back_fields()`) returns to that page, a `fetch()` request gets `204`, and anything else goes to `back_to_list()`, which keeps the view. Messages go through `notify()`, which skips `fetch()` requests. Category `undo` shows an Undo button in the toast. Templates get it as `keep` (add it to links with `**keep`), and `list_url(**changes)` builds a list link with parts changed (`None` removes one).
  - `render_list()` (used by `index()` and by `quick_add()` errors) loads the user's tasks in display order with SQL. The tag filter, search, `matches()` (filter tabs) and `due_badge()` then run in Python. Due dates are `YYYY-MM-DD` and times `HH:MM` strings, so they compare correctly as text.
  - `decorate()` turns task rows into the dicts templates use (badge, color, tags, subtasks, progress). Use it on any page that shows task cards.
  - Tasks are saved through `insert_task()`, which also calls `save_tags()` (tags live in `tags` + `task_tags`) and adds `data["subtasks"]`. Delete tasks with `delete_task_rows()`, which removes the `task_tags` and `subtasks` rows first.
  - `complete_task()` marks a task done (and out of the board's Doing column), inserts the next copy of a repeating task due on `recurrence.next_due_after()`, clears the rule on the done one, and saves undo data. Use it everywhere a task gets completed.
  - `save_undo()` keeps one undoable action per user in the `undo` table, as JSON. `undo()` reverses a complete, or re-inserts a deleted task with its tags and subtasks.
  - `GET /reminders` returns JSON for `static/reminders.js`, which polls it while a page is open.
- `todo/quickadd.py`: `parse_quick_add(text, today)` cuts the repeat, date, time and `#tags` out of a line and leaves the title. `quick_add()` turns the result into form fields and runs `validate_task`, so both paths share one set of checks.
- `todo/recurrence.py`: repeat rules are codes like `day:3`, `week:1:4`, `weekdays` and `nth:2:0`. `parse_repeat()` and `describe_repeat()` must round-trip, because the edit form shows the description.
- `todo/validation.py`: `validate_task(form, today, existing_due_date)` and `validate_registration(form)`, `validate_profile(form)` and `validate_settings(form, best_streak)` return `(data, errors)`, `validate_password_change(form)` returns `(new_password, errors)`, sign-up and the profile share `username_error()` and `password_error()`, and `validate_list_name`, `validate_list_color` and `validate_subtask` return `(value, error)`. It must not import Flask. On errors, the views re-render `form.html` with HTTP 400 and keep the user's input.
  - To add a field, update `schema.sql` (plus `NEW_COLUMNS` in `db.py`), `validate_task`, `insert_task()` and the UPDATE in `edit()`, `task_form()`, and `form.html`. Each field shows its error in `<p class="error" id="{name}-error">`.
- `todo/csrf.py`: every POST form must include `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`. Otherwise the request gets 400.
- Error pages (400, 404) render `error.html` through `error_page()` in `tasks.py`.
- Tests live in `tests/`.
  - The `conftest.py` fixtures are `client` (logged in as alice, user 1), `guest` (the same client, logged out), `other_user` (creates bob), `post` (sends the CSRF token), `add` (inserts directly, skipping validation, for alice unless `user_id=` is given; any other column can be passed too, like `due_time="17:00"`), `fetch` (reads a row) and `tags_of` (a task's tag names). `tests/test_planning.py` adds `make_list`. Task titles in tests must not appear elsewhere on the page ("Later" is a button label), so tests use distinctive ones.
  - Every test runs with today fixed to 2026-10-19.

## Conventions

- Styling: `todo/static/style.css`, with colors as CSS variables on `:root`, `color-mix(in srgb, …)`, with themes and a dark look. `<html data-theme data-appearance>` (from `users.theme` and `users.appearance`) picks them: `[data-theme=...]` changes only the accent variables, and the dark variables are written twice (for `dark`, and for `system` inside `prefers-color-scheme: dark`). Breakpoints: 900px (bottom nav, sheets slide up from the bottom, top nav hidden) and 520px (phones: two-column card grid).
  - Colors: `LIST_COLORS` in `validation.py` names the palette, and each name has a `.color-<name>` class that sets `--tint` (plus `slate` for the Inbox and `accent`). Any element with a color class also gets `--card-bg` (pastel) and `--card-ink` (dark text in the same hue). Lists store a color, tasks use their list's, and `tag_color()` in `tasks.py` picks one for a tag from its letters.
  - Layouts: `session["view"]` is `cards` (a CSS `columns` masonry grid), `list` or `board`, set by `POST /view`. Cards come from `ui.task_card()` and board cards from `ui.board_card()` in `templates/_macros.html`. Don't put attributes other than `class` on the card's `<li>` (tests match it).
  - JavaScript only adds to pages that already work without it: `app.js` (greeting, long press opens the card's `[popover]` menu on release, confetti, board drag), `focus.js` (swipe stack), `reminders.js`. It reads the CSRF token from `<meta name="csrf-token">`, and sends `X-Requested-With: fetch` to get a 204 instead of a page.
- Keep comments teaching-oriented but brief. Add or update a test with every behavior change.
