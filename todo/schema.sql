-- IF NOT EXISTS makes this safe to run on every start.

-- One row per account. The password itself is never stored, only a hash
-- of it (see auth.py).
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,  -- "Ana" and "ana" count as the same name
  password_hash TEXT    NOT NULL,
  created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
  theme         TEXT    NOT NULL DEFAULT 'default',  -- one of THEMES in validation.py
  appearance    TEXT    NOT NULL DEFAULT 'system',   -- 'light', 'dark', or 'system' to follow the device
  display_name  TEXT,                                -- "Janelle", shown instead of the username; NULL = none
  avatar        TEXT,                                -- an emoji like '🦊', or NULL for the first letter
  is_demo       INTEGER NOT NULL DEFAULT 0           -- 1 = made by "Try the Demo", deleted after a day
);

-- Lists (projects) like "Work" or "Home". Tasks in no list are in the Inbox.
CREATE TABLE IF NOT EXISTS lists (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users (id),
  name    TEXT    NOT NULL COLLATE NOCASE,
  color   TEXT    NOT NULL DEFAULT 'blue',         -- one of LIST_COLORS in validation.py
  UNIQUE (user_id, name)  -- two people can each have a "Work" list, but one person can't have two
);

-- Every task belongs to one user, through user_id.
CREATE TABLE IF NOT EXISTS tasks (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       INTEGER NOT NULL REFERENCES users (id),
  title         TEXT    NOT NULL,
  description   TEXT    NOT NULL DEFAULT '',
  due_date      TEXT,                              -- 'YYYY-MM-DD', or NULL for no due date
  completed     INTEGER NOT NULL DEFAULT 0,        -- SQLite has no boolean: 0 = no, 1 = yes
  created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
  completed_at  TEXT,                              -- set when the task is marked done
  list_id       INTEGER REFERENCES lists (id),     -- NULL = Inbox
  due_time      TEXT,                              -- 'HH:MM' on a 24-hour clock, or NULL
  repeat        TEXT,                              -- a rule like 'week:1' (see recurrence.py), or NULL
  remind_before INTEGER,                           -- minutes before the due time, or NULL for no reminder
  priority      INTEGER NOT NULL DEFAULT 0,        -- 1 = high priority
  emoji         TEXT,                              -- like '🛒', or NULL
  doing         INTEGER NOT NULL DEFAULT 0         -- 1 = in the board's "Doing" column
);

-- A task's checklist: "buy eggs", "buy milk" inside "Groceries".
CREATE TABLE IF NOT EXISTS subtasks (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES tasks (id),
  title   TEXT    NOT NULL,
  done    INTEGER NOT NULL DEFAULT 0
);

-- The last thing each user can undo (completing or deleting a task).
-- It's saved as JSON text: a dict turned into a string by json.dumps().
CREATE TABLE IF NOT EXISTS undo (
  user_id INTEGER PRIMARY KEY REFERENCES users (id),  -- one row per user: a new action replaces the old one
  data    TEXT    NOT NULL
);

-- Tags are a "many-to-many" link: a task can have many tags, and a tag can
-- be on many tasks. So the links get their own table, one row per pair.
CREATE TABLE IF NOT EXISTS tags (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users (id),
  name    TEXT    NOT NULL,                        -- saved in lowercase, without the #
  UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS task_tags (
  task_id INTEGER NOT NULL REFERENCES tasks (id),
  tag_id  INTEGER NOT NULL REFERENCES tags (id),
  PRIMARY KEY (task_id, tag_id)                    -- the same tag can't be on a task twice
);
