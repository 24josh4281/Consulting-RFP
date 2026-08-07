from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import Notice


SCHEMA = """
CREATE TABLE IF NOT EXISTS notices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT NOT NULL,
  source_name TEXT NOT NULL,
  external_id TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  published_at TEXT,
  deadline_at TEXT,
  buyer TEXT,
  budget TEXT,
  procurement_method TEXT,
  category TEXT,
  relevance_score INTEGER NOT NULL DEFAULT 0,
  matched_keywords TEXT NOT NULL DEFAULT '[]',
  review_status TEXT NOT NULL DEFAULT 'new',
  review_note TEXT NOT NULL DEFAULT '',
  reviewed_at TEXT,
  raw_json TEXT NOT NULL DEFAULT '{}',
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  UNIQUE(source_id, external_id)
);

CREATE TABLE IF NOT EXISTS attachments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  notice_id INTEGER NOT NULL,
  label TEXT NOT NULL,
  url TEXT NOT NULL,
  file_type TEXT,
  UNIQUE(notice_id, url),
  FOREIGN KEY(notice_id) REFERENCES notices(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  source_count INTEGER NOT NULL DEFAULT 0,
  notice_count INTEGER NOT NULL DEFAULT 0,
  inserted_or_updated_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  message TEXT
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    ensure_review_columns(connection)
    return connection


def ensure_review_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(notices)").fetchall()
    }
    migrations = {
        "review_status": "ALTER TABLE notices ADD COLUMN review_status TEXT NOT NULL DEFAULT 'new'",
        "review_note": "ALTER TABLE notices ADD COLUMN review_note TEXT NOT NULL DEFAULT ''",
        "reviewed_at": "ALTER TABLE notices ADD COLUMN reviewed_at TEXT",
    }
    for column_name, statement in migrations.items():
        if column_name not in existing_columns:
            connection.execute(statement)
    connection.commit()


def start_run(connection: sqlite3.Connection, source_count: int) -> int:
    cursor = connection.execute(
        "INSERT INTO sync_runs (started_at, source_count, status) VALUES (?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), source_count, "running"),
    )
    connection.commit()
    return int(cursor.lastrowid)


def finish_run(
    connection: sqlite3.Connection,
    run_id: int,
    notice_count: int,
    inserted_or_updated_count: int,
    status: str = "success",
    message: str = "",
) -> None:
    connection.execute(
        """
        UPDATE sync_runs
        SET finished_at = ?, notice_count = ?, inserted_or_updated_count = ?, status = ?, message = ?
        WHERE id = ?
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            notice_count,
            inserted_or_updated_count,
            status,
            message,
            run_id,
        ),
    )
    connection.commit()


def upsert_notice(connection: sqlite3.Connection, notice: Notice) -> bool:
    now = datetime.now().isoformat(timespec="seconds")
    existing = connection.execute(
        "SELECT id FROM notices WHERE source_id = ? AND external_id = ?",
        (notice.source_id, notice.external_id),
    ).fetchone()

    payload = (
        notice.source_id,
        notice.source_name,
        notice.external_id,
        notice.title,
        notice.url,
        notice.published_at,
        notice.deadline_at,
        notice.buyer,
        notice.budget,
        notice.procurement_method,
        notice.category,
        notice.relevance_score,
        json.dumps(notice.matched_keywords, ensure_ascii=False),
        json.dumps(notice.raw, ensure_ascii=False),
        now,
    )

    if existing:
        notice_id = int(existing["id"])
        connection.execute(
            """
            UPDATE notices
            SET source_name = ?, title = ?, url = ?, published_at = ?, deadline_at = ?,
                buyer = ?, budget = ?, procurement_method = ?, category = ?,
                relevance_score = ?, matched_keywords = ?, raw_json = ?, last_seen_at = ?
            WHERE id = ?
            """,
            (
                notice.source_name,
                notice.title,
                notice.url,
                notice.published_at,
                notice.deadline_at,
                notice.buyer,
                notice.budget,
                notice.procurement_method,
                notice.category,
                notice.relevance_score,
                json.dumps(notice.matched_keywords, ensure_ascii=False),
                json.dumps(notice.raw, ensure_ascii=False),
                now,
                notice_id,
            ),
        )
        changed = False
    else:
        cursor = connection.execute(
            """
            INSERT INTO notices (
              source_id, source_name, external_id, title, url, published_at, deadline_at,
              buyer, budget, procurement_method, category, relevance_score,
              matched_keywords, raw_json, first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload + (now,),
        )
        notice_id = int(cursor.lastrowid)
        changed = True

    for attachment in notice.attachments:
        connection.execute(
            """
            INSERT OR IGNORE INTO attachments (notice_id, label, url, file_type)
            VALUES (?, ?, ?, ?)
            """,
            (notice_id, attachment.label, attachment.url, attachment.file_type),
        )

    connection.commit()
    return changed


def list_notices(
    connection: sqlite3.Connection,
    status: str | None = None,
    min_score: int | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    where_clauses = []
    params: list[object] = []
    if status:
        where_clauses.append("n.review_status = ?")
        params.append(status)
    if min_score is not None:
        where_clauses.append("n.relevance_score >= ?")
        params.append(min_score)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    limit_sql = ""
    if limit is not None:
        limit_sql = "LIMIT ?"
        params.append(limit)

    return list(
        connection.execute(
            f"""
            SELECT n.*,
                   COALESCE(
                     (SELECT json_group_array(json_object('label', a.label, 'url', a.url, 'file_type', a.file_type))
                      FROM attachments a WHERE a.notice_id = n.id),
                     '[]'
                   ) AS attachments_json
            FROM notices n
            {where_sql}
            ORDER BY relevance_score DESC, COALESCE(deadline_at, '') ASC, first_seen_at DESC
            {limit_sql}
            """,
            params,
        )
    )


def update_notice_review(
    connection: sqlite3.Connection,
    notice_id: int,
    review_status: str,
    review_note: str | None = None,
) -> bool:
    existing = connection.execute("SELECT id FROM notices WHERE id = ?", (notice_id,)).fetchone()
    if not existing:
        return False

    if review_note is None:
        connection.execute(
            """
            UPDATE notices
            SET review_status = ?, reviewed_at = ?
            WHERE id = ?
            """,
            (review_status, datetime.now().isoformat(timespec="seconds"), notice_id),
        )
    else:
        connection.execute(
            """
            UPDATE notices
            SET review_status = ?, review_note = ?, reviewed_at = ?
            WHERE id = ?
            """,
            (review_status, review_note, datetime.now().isoformat(timespec="seconds"), notice_id),
        )
    connection.commit()
    return True


def review_stats(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT review_status, COUNT(*) AS count
            FROM notices
            GROUP BY review_status
            ORDER BY count DESC, review_status ASC
            """
        )
    )
