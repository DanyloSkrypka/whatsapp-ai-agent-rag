"""SQLite storage: clients (language, lead state), full dialog history, leads, hand-overs."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_key TEXT UNIQUE NOT NULL,
  profile_name TEXT,
  lang TEXT,
  state TEXT NOT NULL DEFAULT '{}',
  created TEXT NOT NULL,
  last_in TEXT
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id INTEGER NOT NULL REFERENCES clients(id),
  role TEXT NOT NULL,            -- user | bot | manager
  text TEXT NOT NULL,
  meta TEXT NOT NULL DEFAULT '{}',
  ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_messages_client ON messages(client_id, id);
CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id INTEGER NOT NULL REFERENCES clients(id),
  name TEXT, task TEXT, budget TEXT, budget_eur INTEGER,
  status TEXT NOT NULL,          -- hot | warm
  lang TEXT,
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS handoffs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id INTEGER NOT NULL REFERENCES clients(id),
  question TEXT NOT NULL,
  best_score REAL,
  created TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.con.executescript(SCHEMA)

    def _x(self, sql: str, args=()):
        with self.lock:
            cur = self.con.execute(sql, args)
            self.con.commit()
            return cur

    # ---- clients
    def client(self, user_key: str, profile_name: Optional[str] = None) -> dict:
        row = self._x("SELECT * FROM clients WHERE user_key=?", (user_key,)).fetchone()
        if not row:
            self._x("INSERT INTO clients (user_key, profile_name, created) VALUES (?,?,?)",
                    (user_key, profile_name, now_iso()))
            row = self._x("SELECT * FROM clients WHERE user_key=?", (user_key,)).fetchone()
        elif profile_name and not row["profile_name"]:
            self._x("UPDATE clients SET profile_name=? WHERE id=?", (profile_name, row["id"]))
        d = dict(row)
        d["state"] = json.loads(d["state"] or "{}")
        return d

    def client_by_id(self, cid: int) -> Optional[dict]:
        row = self._x("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["state"] = json.loads(d["state"] or "{}")
        return d

    def save_client(self, c: dict) -> None:
        self._x("UPDATE clients SET lang=?, state=?, last_in=? WHERE id=?",
                (c.get("lang"), json.dumps(c["state"], ensure_ascii=False), c.get("last_in"), c["id"]))

    # ---- history
    def add_message(self, client_id: int, role: str, text: str, meta: Optional[dict] = None) -> None:
        self._x("INSERT INTO messages (client_id, role, text, meta, ts) VALUES (?,?,?,?,?)",
                (client_id, role, text, json.dumps(meta or {}, ensure_ascii=False), now_iso()))

    def history(self, client_id: int, limit: int = 20) -> list[dict]:
        rows = self._x("SELECT role, text, meta, ts FROM messages WHERE client_id=? ORDER BY id DESC LIMIT ?",
                       (client_id, limit)).fetchall()
        return [dict(r, meta=json.loads(r["meta"])) for r in reversed(rows)]

    # ---- leads / hand-overs
    def add_lead(self, client_id: int, name, task, budget, budget_eur, status, lang) -> int:
        cur = self._x("INSERT INTO leads (client_id, name, task, budget, budget_eur, status, lang, created) "
                      "VALUES (?,?,?,?,?,?,?,?)", (client_id, name, task, budget, budget_eur, status, lang, now_iso()))
        return cur.lastrowid

    def leads(self) -> list[dict]:
        return [dict(r) for r in self._x(
            "SELECT l.*, c.user_key FROM leads l JOIN clients c ON c.id=l.client_id ORDER BY l.id").fetchall()]

    def add_handoff(self, client_id: int, question: str, best_score: Optional[float]) -> int:
        return self._x("INSERT INTO handoffs (client_id, question, best_score, created) VALUES (?,?,?,?)",
                       (client_id, question, best_score, now_iso())).lastrowid

    def handoffs(self) -> list[dict]:
        return [dict(r) for r in self._x("SELECT * FROM handoffs ORDER BY id").fetchall()]
