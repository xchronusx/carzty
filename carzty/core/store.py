##xchronusx
"""
carzty.core.store - sqlite. where your unfinished business lives.

Synopsis:
    store = Store("data/carzty.db")
    task = store.add(task)
    store.save(task)
    store.due(now)

Description:
    One sqlite file, WAL mode, a couple tables. Migrations ride on PRAGMA
    user_version, so adding a column later is "append a SQL string to MIGRATIONS"
    and nothing fancier.

    Yes, it's synchronous. It's sqlite with a few hundred rows and queries that
    take microseconds. Wrapping that in threads to feel async is cosplay.

Notes:
    Author: Zachary Wright (xchronusx)
    Every user-facing lookup is scoped by user_id. Nobody gets to touch anybody else's tasks.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import fields
from pathlib import Path

from carzty.core.models import ACTIVE, DONE, Task

#region SCHEMA

MIGRATIONS: list[str] = [
    # v1 - the whole thing
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id                 INTEGER NOT NULL,
        title                   TEXT    NOT NULL,
        notes                   TEXT,
        tz                      TEXT    NOT NULL,
        created_at              INTEGER NOT NULL,
        interval_seconds        INTEGER,
        weekdays                TEXT,
        next_due                INTEGER,
        nag_seconds             INTEGER,
        followup_at             INTEGER,
        followup_kind           TEXT,
        pending                 INTEGER NOT NULL DEFAULT 0,
        nag_count               INTEGER NOT NULL DEFAULT 0,
        state                   TEXT    NOT NULL DEFAULT 'active',
        deliver                 TEXT    NOT NULL DEFAULT 'dm',
        guild_id                INTEGER,
        channel_id              INTEGER,
        last_fired_at           INTEGER,
        last_done_at            INTEGER,
        times_fired             INTEGER NOT NULL DEFAULT 0,
        times_done              INTEGER NOT NULL DEFAULT 0,
        streak                  INTEGER NOT NULL DEFAULT 0,
        last_message_id         INTEGER,
        last_message_channel_id INTEGER,
        last_error              TEXT,
        updated_at              INTEGER
    );
    CREATE INDEX IF NOT EXISTS ix_tasks_user     ON tasks (user_id, state);
    CREATE INDEX IF NOT EXISTS ix_tasks_due      ON tasks (state, next_due);
    CREATE INDEX IF NOT EXISTS ix_tasks_followup ON tasks (state, followup_at);

    CREATE TABLE IF NOT EXISTS users (
        user_id    INTEGER PRIMARY KEY,
        tz         TEXT,
        tone       TEXT,
        updated_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    );
    """,
]

_TASK_COLUMNS = [f.name for f in fields(Task) if f.name != "id"]

#endregion


def _weekdays_to_db(value: tuple[int, ...] | None) -> str | None:
    return ",".join(str(d) for d in value) if value else None


def _weekdays_from_db(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    return tuple(int(x) for x in value.split(",") if x.strip() != "")


def _row_to_task(row: sqlite3.Row) -> Task:
    data = {name: row[name] for name in _TASK_COLUMNS}
    data["weekdays"] = _weekdays_from_db(data["weekdays"])
    data["pending"] = bool(data["pending"])
    return Task(id=row["id"], **data)


def _task_to_params(task: Task) -> dict:
    data = {name: getattr(task, name) for name in _TASK_COLUMNS}
    data["weekdays"] = _weekdays_to_db(task.weekdays)
    data["pending"] = 1 if task.pending else 0
    return data


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self.db.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    #region PLUMBING

    def _migrate(self) -> None:
        with self._lock:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            for idx, script in enumerate(MIGRATIONS[version:], start=version + 1):
                self.db.executescript("BEGIN;" + script + f"PRAGMA user_version = {idx}; COMMIT;")

    @property
    def schema_version(self) -> int:
        return self.db.execute("PRAGMA user_version").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self.db.close()

    #endregion

    #region TASKS

    def add(self, task: Task, now: int | None = None) -> Task:
        params = _task_to_params(task)
        params["updated_at"] = now or task.created_at
        cols = list(params)
        sql = f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"
        with self._lock:
            cur = self.db.execute(sql, params)
            new_id = cur.lastrowid
        return self.get(new_id)

    def save(self, task: Task, now: int | None = None) -> Task:
        if task.id is None:
            raise ValueError("can't save a task that was never added")
        params = _task_to_params(task)
        params["updated_at"] = now
        sets = ", ".join(f"{c} = :{c}" for c in params)
        params["id"] = task.id
        with self._lock:
            self.db.execute(f"UPDATE tasks SET {sets} WHERE id = :id", params)
        return task

    def get(self, task_id: int) -> Task | None:
        with self._lock:
            row = self.db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_to_task(row) if row else None

    def get_for_user(self, task_id: int, user_id: int) -> Task | None:
        with self._lock:
            row = self.db.execute(
                "SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
            ).fetchone()
        return _row_to_task(row) if row else None

    def list_for_user(self, user_id: int, include_done: bool = False, limit: int = 100) -> list[Task]:
        sql = "SELECT * FROM tasks WHERE user_id = ?"
        if not include_done:
            sql += f" AND state != '{DONE}'"
        # ringing first, then soonest, then whatever's left
        sql += """
            ORDER BY
                CASE state WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,
                pending DESC,
                COALESCE(next_due, followup_at, 9999999999),
                id
            LIMIT ?
        """
        with self._lock:
            rows = self.db.execute(sql, (user_id, limit)).fetchall()
        return [_row_to_task(r) for r in rows]

    def count_open(self, user_id: int) -> int:
        with self._lock:
            return self.db.execute(
                "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND state != ?", (user_id, DONE)
            ).fetchone()[0]

    def search_for_user(self, user_id: int, text: str, include_done: bool = False, limit: int = 25) -> list[Task]:
        """Autocomplete fodder. Matches on title or #id."""
        text = (text or "").strip().lstrip("#")
        params: list = [user_id]
        sql = "SELECT * FROM tasks WHERE user_id = ?"
        if not include_done:
            sql += f" AND state != '{DONE}'"
        if text:
            sql += " AND (title LIKE ? ESCAPE '\\' OR CAST(id AS TEXT) = ?)"
            escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params += [f"%{escaped}%", text]
        sql += " ORDER BY pending DESC, COALESCE(next_due, followup_at, 9999999999), id LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self.db.execute(sql, params).fetchall()
        return [_row_to_task(r) for r in rows]

    def due(self, now: int, limit: int = 200) -> list[Task]:
        with self._lock:
            rows = self.db.execute(
                """
                SELECT * FROM tasks
                WHERE state = ?
                  AND ((next_due IS NOT NULL AND next_due <= ?)
                    OR (followup_at IS NOT NULL AND followup_at <= ?))
                ORDER BY MIN(COALESCE(next_due, 9999999999), COALESCE(followup_at, 9999999999))
                LIMIT ?
                """,
                (ACTIVE, now, now, limit),
            ).fetchall()
        return [_row_to_task(r) for r in rows]

    def delete(self, task_id: int, user_id: int) -> bool:
        with self._lock:
            cur = self.db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
        return cur.rowcount > 0

    def purge_done(self, older_than: int) -> int:
        """Bin finished tasks that have been sitting around since before `older_than`."""
        with self._lock:
            cur = self.db.execute(
                "DELETE FROM tasks WHERE state = ? AND COALESCE(last_done_at, updated_at, created_at) < ?",
                (DONE, older_than),
            )
        return cur.rowcount

    #endregion

    #region USERS + META

    def get_user(self, user_id: int) -> dict:
        with self._lock:
            row = self.db.execute("SELECT tz, tone FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return {"tz": row["tz"], "tone": row["tone"]} if row else {"tz": None, "tone": None}

    def set_user(self, user_id: int, now: int, tz: str | None = None, tone: str | None = None) -> None:
        current = self.get_user(user_id)
        tz = tz if tz is not None else current["tz"]
        tone = tone if tone is not None else current["tone"]
        with self._lock:
            self.db.execute(
                """
                INSERT INTO users (user_id, tz, tone, updated_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET tz = excluded.tz, tone = excluded.tone, updated_at = excluded.updated_at
                """,
                (user_id, tz, tone, now),
            )

    def get_meta(self, key: str) -> str | None:
        with self._lock:
            row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self.db.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def stats(self) -> dict:
        with self._lock:
            row = self.db.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(state = 'active') AS active,
                       SUM(state = 'paused') AS paused,
                       SUM(state = 'done')   AS done,
                       COUNT(DISTINCT user_id) AS users
                FROM tasks
                """
            ).fetchone()
        return {k: (row[k] or 0) for k in row.keys()}  # noqa: SIM118 - sqlite3.Row iterates values, not keys

    #endregion
##xchronusx
