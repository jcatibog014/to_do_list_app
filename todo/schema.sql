-- IF NOT EXISTS makes this safe to run on every start.

-- One row per account. The password itself is never stored, only a hash
-- of it (see auth.py).
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,  -- "Ana" and "ana" count as the same name
  password_hash TEXT    NOT NULL,
  created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Every task belongs to one user, through user_id.
CREATE TABLE IF NOT EXISTS tasks (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      INTEGER NOT NULL REFERENCES users (id),
  title        TEXT    NOT NULL,
  description  TEXT    NOT NULL DEFAULT '',
  due_date     TEXT,                              -- 'YYYY-MM-DD', or NULL for no due date
  completed    INTEGER NOT NULL DEFAULT 0,        -- SQLite has no boolean: 0 = no, 1 = yes
  created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
  completed_at TEXT                               -- set when the task is marked done
);
