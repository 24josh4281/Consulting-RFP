from __future__ import annotations

import json
import re
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

CREATE TABLE IF NOT EXISTS notification_settings (
  setting_key TEXT PRIMARY KEY,
  setting_value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  notification_type TEXT NOT NULL,
  notification_key TEXT NOT NULL,
  notice_id INTEGER,
  recipient TEXT NOT NULL,
  subject TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  sent_at TEXT,
  error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE(notification_type, notification_key, recipient),
  FOREIGN KEY(notice_id) REFERENCES notices(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_notification_deliveries_lookup
ON notification_deliveries(notification_type, notification_key, recipient, status);
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

    _upsert_attachments(connection, notice_id, notice)

    connection.commit()
    return changed


def _attachment_identity(label: str, url: str) -> str:
    """Make public download URLs stable when a portal rotates its token parameter."""
    normalized_label = re.sub(r"\s+", " ", label or "").strip().casefold()
    file_sequence_match = re.search(r"(?:[?&]fileSeq=)([^&#]+)", url or "", flags=re.IGNORECASE)
    file_sequence = file_sequence_match.group(1) if file_sequence_match else ""
    return f"{normalized_label}|{file_sequence}" if normalized_label else f"url|{url}"


def _upsert_attachments(connection: sqlite3.Connection, notice_id: int, notice: Notice) -> None:
    """Refresh collected attachment URLs without duplicating tokenized official downloads.

    Review fields live on ``notices`` and are never affected here. Existing files that a
    source did not return in this one run are retained; only exact duplicate auto-collected
    attachment identities are consolidated.
    """
    existing_by_identity: dict[str, sqlite3.Row] = {}
    duplicate_ids: list[int] = []
    for row in connection.execute(
        "SELECT id, label, url, file_type FROM attachments WHERE notice_id = ? ORDER BY id",
        (notice_id,),
    ).fetchall():
        identity = _attachment_identity(str(row["label"]), str(row["url"]))
        if identity in existing_by_identity:
            duplicate_ids.append(int(row["id"]))
        else:
            existing_by_identity[identity] = row

    for attachment_id in duplicate_ids:
        connection.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))

    for attachment in notice.attachments:
        identity = _attachment_identity(attachment.label, attachment.url)
        existing = existing_by_identity.get(identity)
        if existing:
            connection.execute(
                """
                UPDATE attachments
                SET label = ?, url = ?, file_type = ?
                WHERE id = ?
                """,
                (attachment.label, attachment.url, attachment.file_type, int(existing["id"])),
            )
            continue
        connection.execute(
            """
            INSERT OR IGNORE INTO attachments (notice_id, label, url, file_type)
            VALUES (?, ?, ?, ?)
            """,
            (notice_id, attachment.label, attachment.url, attachment.file_type),
        )


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


def _notification_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def get_notification_setting(connection: sqlite3.Connection, setting_key: str) -> str | None:
    row = connection.execute(
        "SELECT setting_value FROM notification_settings WHERE setting_key = ?",
        (setting_key,),
    ).fetchone()
    return str(row["setting_value"]) if row else None


def set_notification_setting(connection: sqlite3.Connection, setting_key: str, setting_value: str) -> None:
    connection.execute(
        """
        INSERT INTO notification_settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
          setting_value = excluded.setting_value,
          updated_at = excluded.updated_at
        """,
        (setting_key, setting_value, _notification_now()),
    )
    connection.commit()


def notification_delivery_sent(
    connection: sqlite3.Connection,
    notification_type: str,
    notification_key: str,
    recipient: str,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM notification_deliveries
        WHERE notification_type = ? AND notification_key = ? AND recipient = ? AND status = 'sent'
        """,
        (notification_type, notification_key, recipient),
    ).fetchone()
    return row is not None


def record_notification_delivery(
    connection: sqlite3.Connection,
    *,
    notification_type: str,
    notification_key: str,
    recipient: str,
    subject: str,
    notice_id: int | None = None,
    status: str = "sent",
    error: str = "",
) -> None:
    now = _notification_now()
    sent_at = now if status == "sent" else None
    connection.execute(
        """
        INSERT INTO notification_deliveries (
          notification_type, notification_key, notice_id, recipient, subject,
          status, sent_at, error, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(notification_type, notification_key, recipient) DO UPDATE SET
          notice_id = excluded.notice_id,
          subject = excluded.subject,
          status = excluded.status,
          sent_at = excluded.sent_at,
          error = excluded.error,
          created_at = excluded.created_at
        """,
        (
            notification_type,
            notification_key,
            notice_id,
            recipient,
            subject,
            status,
            sent_at,
            error,
            now,
        ),
    )
    connection.commit()


def last_successful_notification_at(
    connection: sqlite3.Connection,
    notification_type: str,
    recipient: str,
) -> str | None:
    row = connection.execute(
        """
        SELECT sent_at
        FROM notification_deliveries
        WHERE notification_type = ? AND recipient = ? AND status = 'sent' AND sent_at IS NOT NULL
        ORDER BY sent_at DESC
        LIMIT 1
        """,
        (notification_type, recipient),
    ).fetchone()
    return str(row["sent_at"]) if row else None


def list_notices_since(
    connection: sqlite3.Connection,
    since_at: str,
    *,
    min_score: int = 0,
) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT n.*,
                   COALESCE(
                     (SELECT json_group_array(json_object('label', a.label, 'url', a.url, 'file_type', a.file_type))
                      FROM attachments a WHERE a.notice_id = n.id),
                     '[]'
                   ) AS attachments_json
            FROM notices n
            WHERE n.first_seen_at > ?
              AND n.relevance_score >= ?
              AND n.review_status NOT IN ('not_relevant', 'closed')
            ORDER BY relevance_score DESC, COALESCE(deadline_at, '') ASC, first_seen_at ASC
            """,
            (since_at, min_score),
        )
    )


def list_unnotified_notices(
    connection: sqlite3.Connection,
    *,
    recipient: str,
    baseline_at: str,
    min_score: int = 0,
) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT n.*,
                   COALESCE(
                     (SELECT json_group_array(json_object('label', a.label, 'url', a.url, 'file_type', a.file_type))
                      FROM attachments a WHERE a.notice_id = n.id),
                     '[]'
                   ) AS attachments_json
            FROM notices n
            WHERE n.first_seen_at > ?
              AND n.relevance_score >= ?
              AND n.review_status NOT IN ('not_relevant', 'closed')
              AND NOT EXISTS (
                SELECT 1
                FROM notification_deliveries d
                WHERE d.notification_type = 'immediate'
                  AND d.notification_key = CAST(n.id AS TEXT)
                  AND d.recipient = ?
                  AND d.status = 'sent'
              )
            ORDER BY relevance_score DESC, COALESCE(deadline_at, '') ASC, first_seen_at ASC
            """,
            (baseline_at, min_score, recipient),
        )
    )
