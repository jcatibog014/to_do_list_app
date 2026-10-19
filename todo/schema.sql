-- One table holds every task.
-- IF NOT EXISTS makes this safe to run on every start.
CREATE TABLE IF NOT EXISTS tasks (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title        TEXT    NOT NULL,
  description  TEXT    NOT NULL DEFAULT '',
  due_date     TEXT,                              -- 'YYYY-MM-DD', or NULL for no due date
  completed    INTEGER NOT NULL DEFAULT 0,        -- SQLite has no boolean: 0 = no, 1 = yes
  created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
  completed_at TEXT                               -- set when the task is marked done
);
