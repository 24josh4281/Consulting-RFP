from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import Attachment, Notice


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
  business_tier TEXT NOT NULL DEFAULT 'unclassified',
  tier_reason TEXT NOT NULL DEFAULT '',
  tier_source TEXT NOT NULL DEFAULT 'automatic',
  tiered_at TEXT,
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

CREATE TABLE IF NOT EXISTS document_insights (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  notice_id INTEGER NOT NULL,
  attachment_id INTEGER,
  document_url TEXT NOT NULL,
  document_label TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  extraction_status TEXT NOT NULL DEFAULT 'not_attempted',
  task_summary TEXT NOT NULL DEFAULT '',
  amount_value_krw INTEGER,
  amount_text TEXT NOT NULL DEFAULT '',
  amount_basis TEXT NOT NULL DEFAULT '',
  evidence_excerpt TEXT NOT NULL DEFAULT '',
  extracted_at TEXT,
  error_message TEXT NOT NULL DEFAULT '',
  cache_path TEXT NOT NULL DEFAULT '',
  UNIQUE(notice_id, document_url),
  FOREIGN KEY(notice_id) REFERENCES notices(id) ON DELETE CASCADE,
  FOREIGN KEY(attachment_id) REFERENCES attachments(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_document_insights_notice
ON document_insights(notice_id, extraction_status, extracted_at);

CREATE TABLE IF NOT EXISTS bid_fit_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  notice_id INTEGER NOT NULL UNIQUE,
  consulting_fit TEXT NOT NULL DEFAULT 'not_reviewed',
  qualification_requirements TEXT NOT NULL DEFAULT '',
  proposed_team TEXT NOT NULL DEFAULT '',
  bid_decision TEXT NOT NULL DEFAULT 'pending',
  key_risks TEXT NOT NULL DEFAULT '',
  decision_note TEXT NOT NULL DEFAULT '',
  updated_at TEXT,
  FOREIGN KEY(notice_id) REFERENCES notices(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bid_fit_reviews_notice
ON bid_fit_reviews(notice_id, bid_decision, consulting_fit);

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
    ensure_tier_columns(connection)
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


def ensure_tier_columns(connection: sqlite3.Connection) -> None:
    """Add business-fit metadata without changing collected notice/source data."""
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(notices)").fetchall()
    }
    migrations = {
        "business_tier": "ALTER TABLE notices ADD COLUMN business_tier TEXT NOT NULL DEFAULT 'unclassified'",
        "tier_reason": "ALTER TABLE notices ADD COLUMN tier_reason TEXT NOT NULL DEFAULT ''",
        "tier_source": "ALTER TABLE notices ADD COLUMN tier_source TEXT NOT NULL DEFAULT 'automatic'",
        "tiered_at": "ALTER TABLE notices ADD COLUMN tiered_at TEXT",
    }
    for column_name, statement in migrations.items():
        if column_name not in existing_columns:
            connection.execute(statement)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_notices_business_tier "
        "ON notices(business_tier, review_status, relevance_score)"
    )
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
        "SELECT id, tier_source FROM notices WHERE source_id = ? AND external_id = ?",
        (notice.source_id, notice.external_id),
    ).fetchone()
    tier_source = notice.tier_source if notice.tier_source in {"automatic", "manual"} else "automatic"
    tiered_at = notice.tiered_at or now

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
        notice.review_status or "new",
        notice.review_note or "",
        notice.business_tier or "unclassified",
        notice.tier_reason or "",
        tier_source,
        tiered_at,
        json.dumps(notice.raw, ensure_ascii=False),
        now,
    )

    if existing:
        notice_id = int(existing["id"])
        update_params = [
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
        ]
        tier_update_sql = ""
        if str(existing["tier_source"] or "automatic") != "manual":
            tier_update_sql = ", business_tier = ?, tier_reason = ?, tier_source = ?, tiered_at = ?"
            update_params.extend(
                [
                    notice.business_tier or "unclassified",
                    notice.tier_reason or "",
                    tier_source,
                    tiered_at,
                ]
            )
        update_params.append(notice_id)
        connection.execute(
            """
            UPDATE notices
            SET source_name = ?, title = ?, url = ?, published_at = ?, deadline_at = ?,
                buyer = ?, budget = ?, procurement_method = ?, category = ?,
                relevance_score = ?, matched_keywords = ?, raw_json = ?, last_seen_at = ?
            """
            + tier_update_sql
            + " WHERE id = ?",
            update_params,
        )
        changed = False
    else:
        cursor = connection.execute(
            """
            INSERT INTO notices (
              source_id, source_name, external_id, title, url, published_at, deadline_at,
              buyer, budget, procurement_method, category, relevance_score,
              matched_keywords, review_status, review_note,
              business_tier, tier_reason, tier_source, tiered_at,
              raw_json, first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload + (now,),
        )
        notice_id = int(cursor.lastrowid)
        changed = True

    _upsert_attachments(connection, notice_id, notice.attachments)

    connection.commit()
    return changed


def _attachment_identity(label: str, url: str) -> str:
    """Make public download URLs stable when a portal rotates its token parameter."""
    normalized_label = re.sub(r"\s+", " ", label or "").strip().casefold()
    file_sequence_match = re.search(r"(?:[?&]fileSeq=)([^&#]+)", url or "", flags=re.IGNORECASE)
    file_sequence = file_sequence_match.group(1) if file_sequence_match else ""
    return f"{normalized_label}|{file_sequence}" if normalized_label else f"url|{url}"


def _upsert_attachments(
    connection: sqlite3.Connection,
    notice_id: int,
    attachments: list[Attachment],
) -> dict[str, int]:
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

    added = 0
    updated = 0
    for attachment in attachments:
        if not attachment.url:
            continue
        identity = _attachment_identity(attachment.label, attachment.url)
        existing = existing_by_identity.get(identity)
        if existing:
            if (
                str(existing["label"] or "") != attachment.label
                or str(existing["url"] or "") != attachment.url
                or str(existing["file_type"] or "") != attachment.file_type
            ):
                updated += 1
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
        added += 1
    return {"added": added, "updated": updated, "deduplicated": len(duplicate_ids)}


def upsert_attachments_for_notice(
    connection: sqlite3.Connection,
    notice_id: int,
    attachments: list[Attachment],
) -> dict[str, int]:
    """Add or refresh source attachment facts for an existing notice only.

    This intentionally does not touch notice metadata, review state, Tier metadata,
    or document-derived evidence.  It is used by the saved G2B raw-response
    backfill path.
    """
    existing = connection.execute("SELECT id FROM notices WHERE id = ?", (notice_id,)).fetchone()
    if not existing:
        return {"added": 0, "updated": 0, "deduplicated": 0, "missing_notice": 1}
    result = _upsert_attachments(connection, notice_id, attachments)
    connection.commit()
    return {**result, "missing_notice": 0}


VALID_CONSULTING_FITS = {"not_reviewed", "high", "medium", "low"}
VALID_BID_DECISIONS = {"pending", "bid", "conditional", "no_bid"}


def get_bid_fit_review(connection: sqlite3.Connection, notice_id: int) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM bid_fit_reviews WHERE notice_id = ?",
        (notice_id,),
    ).fetchone()


def upsert_bid_fit_review(
    connection: sqlite3.Connection,
    *,
    notice_id: int,
    consulting_fit: str = "not_reviewed",
    qualification_requirements: str = "",
    proposed_team: str = "",
    bid_decision: str = "pending",
    key_risks: str = "",
    decision_note: str = "",
) -> bool:
    """Save a human bid-fit judgement separately from collected source facts."""
    if consulting_fit not in VALID_CONSULTING_FITS:
        raise ValueError(f"Unknown consulting fit: {consulting_fit}")
    if bid_decision not in VALID_BID_DECISIONS:
        raise ValueError(f"Unknown bid decision: {bid_decision}")
    existing_notice = connection.execute("SELECT id FROM notices WHERE id = ?", (notice_id,)).fetchone()
    if not existing_notice:
        return False
    connection.execute(
        """
        INSERT INTO bid_fit_reviews (
          notice_id, consulting_fit, qualification_requirements, proposed_team,
          bid_decision, key_risks, decision_note, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(notice_id) DO UPDATE SET
          consulting_fit = excluded.consulting_fit,
          qualification_requirements = excluded.qualification_requirements,
          proposed_team = excluded.proposed_team,
          bid_decision = excluded.bid_decision,
          key_risks = excluded.key_risks,
          decision_note = excluded.decision_note,
          updated_at = excluded.updated_at
        """,
        (
            notice_id,
            consulting_fit,
            qualification_requirements,
            proposed_team,
            bid_decision,
            key_risks,
            decision_note,
            datetime.now().astimezone().isoformat(timespec="seconds"),
        ),
    )
    connection.commit()
    return True


def list_bid_fit_reviews(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT bfr.*, n.title AS notice_title, n.source_name, n.deadline_at,
                   n.business_tier, n.review_status
            FROM bid_fit_reviews bfr
            JOIN notices n ON n.id = bfr.notice_id
            ORDER BY CASE n.business_tier
                WHEN 'tier_1' THEN 1
                WHEN 'tier_2' THEN 2
                WHEN 'tier_3' THEN 3
                ELSE 4
            END,
            COALESCE(n.deadline_at, ''),
            n.id
            """
        )
    )


def list_notices(
    connection: sqlite3.Connection,
    status: str | None = None,
    business_tier: str | None = None,
    min_score: int | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    where_clauses = []
    params: list[object] = []
    if status:
        where_clauses.append("n.review_status = ?")
        params.append(status)
    if business_tier:
        where_clauses.append("n.business_tier = ?")
        params.append(business_tier)
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


def upsert_document_insight(
    connection: sqlite3.Connection,
    *,
    notice_id: int,
    attachment_id: int | None,
    document_url: str,
    document_label: str,
    source_url: str,
    extraction_status: str,
    task_summary: str = "",
    amount_value_krw: int | None = None,
    amount_text: str = "",
    amount_basis: str = "",
    evidence_excerpt: str = "",
    error_message: str = "",
    cache_path: str = "",
    extracted_at: str | None = None,
) -> None:
    """Store derived document evidence without altering the collected source records."""
    observed_at = extracted_at or datetime.now().astimezone().isoformat(timespec="seconds")
    connection.execute(
        """
        INSERT INTO document_insights (
          notice_id, attachment_id, document_url, document_label, source_url,
          extraction_status, task_summary, amount_value_krw, amount_text,
          amount_basis, evidence_excerpt, extracted_at, error_message, cache_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(notice_id, document_url) DO UPDATE SET
          attachment_id = excluded.attachment_id,
          document_label = excluded.document_label,
          source_url = excluded.source_url,
          extraction_status = excluded.extraction_status,
          task_summary = excluded.task_summary,
          amount_value_krw = excluded.amount_value_krw,
          amount_text = excluded.amount_text,
          amount_basis = excluded.amount_basis,
          evidence_excerpt = excluded.evidence_excerpt,
          extracted_at = excluded.extracted_at,
          error_message = excluded.error_message,
          cache_path = excluded.cache_path
        """,
        (
            notice_id,
            attachment_id,
            document_url,
            document_label,
            source_url,
            extraction_status,
            task_summary,
            amount_value_krw,
            amount_text,
            amount_basis,
            evidence_excerpt,
            observed_at,
            error_message,
            cache_path,
        ),
    )
    connection.commit()


def list_document_insights(
    connection: sqlite3.Connection,
    *,
    notice_id: int | None = None,
) -> list[sqlite3.Row]:
    where_sql = ""
    params: list[object] = []
    if notice_id is not None:
        where_sql = "WHERE di.notice_id = ?"
        params.append(notice_id)
    return list(
        connection.execute(
            f"""
            SELECT di.*,
                   n.title AS notice_title,
                   n.url AS notice_url,
                   n.source_id,
                   n.source_name,
                   n.buyer,
                   n.published_at,
                   n.deadline_at,
                   n.budget AS notice_budget,
                   n.procurement_method,
                   n.business_tier,
                   n.tier_reason,
                   n.review_status,
                   n.review_note,
                   a.file_type AS attachment_file_type
            FROM document_insights di
            JOIN notices n ON n.id = di.notice_id
            LEFT JOIN attachments a ON a.id = di.attachment_id
            {where_sql}
            ORDER BY CASE n.business_tier
                WHEN 'tier_1' THEN 1
                WHEN 'tier_2' THEN 2
                WHEN 'tier_3' THEN 3
                ELSE 4
            END,
            COALESCE(n.deadline_at, '') ASC,
            di.notice_id ASC,
            di.id ASC
            """,
            params,
        )
    )


def list_workbench_notices(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return one row per notice with nested raw attachments and derived insights."""
    return list(
        connection.execute(
            """
            SELECT n.*,
                   COALESCE(
                     (SELECT json_group_array(json_object(
                        'id', a.id,
                        'label', a.label,
                        'url', a.url,
                        'file_type', a.file_type
                      ))
                      FROM attachments a
                      WHERE a.notice_id = n.id),
                     '[]'
                   ) AS attachments_json,
                   COALESCE(
                     (SELECT json_group_array(json_object(
                        'id', di.id,
                        'attachment_id', di.attachment_id,
                        'document_url', di.document_url,
                        'document_label', di.document_label,
                        'source_url', di.source_url,
                        'extraction_status', di.extraction_status,
                        'task_summary', di.task_summary,
                        'amount_value_krw', di.amount_value_krw,
                        'amount_text', di.amount_text,
                        'amount_basis', di.amount_basis,
                        'evidence_excerpt', di.evidence_excerpt,
                        'extracted_at', di.extracted_at,
                        'error_message', di.error_message,
                        'cache_path', di.cache_path
                      ))
                      FROM document_insights di
                      WHERE di.notice_id = n.id),
                     '[]'
                   ) AS insights_json,
                   COALESCE(
                     (SELECT json_object(
                        'consulting_fit', bfr.consulting_fit,
                        'qualification_requirements', bfr.qualification_requirements,
                        'proposed_team', bfr.proposed_team,
                        'bid_decision', bfr.bid_decision,
                        'key_risks', bfr.key_risks,
                        'decision_note', bfr.decision_note,
                        'updated_at', bfr.updated_at
                      )
                      FROM bid_fit_reviews bfr
                      WHERE bfr.notice_id = n.id),
                     '{}'
                   ) AS fit_review_json
            FROM notices n
            ORDER BY CASE n.business_tier
                WHEN 'tier_1' THEN 1
                WHEN 'tier_2' THEN 2
                WHEN 'tier_3' THEN 3
                ELSE 4
            END,
            n.relevance_score DESC,
            COALESCE(n.deadline_at, '') ASC,
            n.first_seen_at DESC
            """
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


def update_notice_tier(
    connection: sqlite3.Connection,
    notice_id: int,
    business_tier: str,
    tier_reason: str,
    *,
    tier_source: str = "manual",
) -> bool:
    """Store a Tier decision without affecting review state or raw source content."""
    existing = connection.execute("SELECT id FROM notices WHERE id = ?", (notice_id,)).fetchone()
    if not existing:
        return False

    connection.execute(
        """
        UPDATE notices
        SET business_tier = ?, tier_reason = ?, tier_source = ?, tiered_at = ?
        WHERE id = ?
        """,
        (
            business_tier,
            tier_reason,
            tier_source,
            datetime.now().isoformat(timespec="seconds"),
            notice_id,
        ),
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


def tier_stats(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT business_tier, COUNT(*) AS count
            FROM notices
            GROUP BY business_tier
            ORDER BY CASE business_tier
                WHEN 'tier_1' THEN 1
                WHEN 'tier_2' THEN 2
                WHEN 'tier_3' THEN 3
                ELSE 4
            END
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
            f"""
            SELECT n.*,
                   COALESCE(
                     (SELECT json_group_array(json_object('label', a.label, 'url', a.url, 'file_type', a.file_type))
                      FROM attachments a WHERE a.notice_id = n.id),
                     '[]'
                   ) AS attachments_json
            FROM notices n
            WHERE n.first_seen_at > ?
              AND n.relevance_score >= ?
              AND n.review_status NOT IN ('not_relevant', 'closed', 'needs_review')
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
    business_tiers: tuple[str, ...] | None = None,
) -> list[sqlite3.Row]:
    tier_sql = ""
    tier_params: list[object] = []
    if business_tiers is not None:
        if not business_tiers:
            return []
        tier_sql = " AND n.business_tier IN (" + ", ".join("?" for _ in business_tiers) + ")"
        tier_params.extend(business_tiers)
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
            WHERE n.first_seen_at > ?
              AND n.relevance_score >= ?
              AND n.review_status NOT IN ('not_relevant', 'closed', 'needs_review')
              {tier_sql}
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
            [baseline_at, min_score, *tier_params, recipient],
        )
    )
