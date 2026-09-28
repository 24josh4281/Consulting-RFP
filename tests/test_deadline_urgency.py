from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from rfp_tracker.briefing import deadline_priority_group, deadline_priority_label, notice_view
from rfp_tracker.documents import build_public_workbench_payload, build_workbench_payload
from rfp_tracker.models import Notice
from rfp_tracker.notifications import _email_deadline_badge, dispatch_notifications, initialize_baseline
from rfp_tracker.render import render_workbench_dashboard
from rfp_tracker.storage import connect, list_notices, upsert_notice


NOW = datetime(2026, 9, 28, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))


def seed_notices(connection) -> None:
    cases = (
        ("day-7", "tier_1", "온실가스 D-7 컨설팅", (NOW + timedelta(days=7)).date().isoformat()),
        ("day-4", "tier_2", "온실가스 D-4 설비 지원", (NOW + timedelta(days=4)).date().isoformat()),
        ("day-2", "tier_2", "온실가스 D-2 융자 지원", (NOW + timedelta(days=2)).date().isoformat()),
        ("day-0", "tier_1", "배출권 D-DAY 컨설팅", NOW.date().isoformat()),
        ("tier-3", "tier_3", "기후변화 D-1 영상 제작", (NOW + timedelta(days=1)).date().isoformat()),
        ("day-8", "tier_1", "온실가스 D-8 컨설팅", (NOW + timedelta(days=8)).date().isoformat()),
        ("closed-today", "tier_1", "온실가스 오늘 마감 경과", (NOW - timedelta(hours=1)).isoformat()),
    )
    for external_id, tier, title, deadline in cases:
        upsert_notice(
            connection,
            Notice(
                source_id="official_board",
                source_name="공식 공고",
                external_id=external_id,
                title=title,
                url=f"https://official.example/{external_id}",
                deadline_at=deadline,
                business_tier=tier,
                relevance_score=7,
            ),
        )


class DeadlineUrgencyTests(unittest.TestCase):
    def test_all_calendar_day_labels_and_colour_bands(self) -> None:
        expected = {
            None: ("", ""),
            -1: ("", ""),
            0: ("D-DAY", "deep-red"),
            1: ("D-1", "red"),
            2: ("D-2", "red"),
            3: ("D-3", "red"),
            4: ("D-4", "yellow"),
            5: ("D-5", "yellow"),
            6: ("D-6", "yellow"),
            7: ("D-7", "yellow"),
            8: ("", ""),
        }
        for days, (label, group) in expected.items():
            with self.subTest(days=days):
                self.assertEqual(deadline_priority_label(days), label)
                self.assertEqual(deadline_priority_group(label), group)

    def test_public_and_internal_urgent_lists_exclude_tier_3_and_closed_notices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            connection = connect(root / "tracker.db")
            seed_notices(connection)
            with patch("rfp_tracker.documents.seoul_now", return_value=NOW):
                public = build_public_workbench_payload(connection)
                internal = build_workbench_payload(connection)
            public_path = root / "public.html"
            internal_path = root / "internal.html"
            render_workbench_dashboard(public, public_path, public=True)
            render_workbench_dashboard(internal, internal_path)
            rendered = public_path.read_text(encoding="utf-8")
            public_urgent = rendered.split('<section id="urgent-deadlines"', 1)[1].split("</section>", 1)[0]
            internal_urgent = internal_path.read_text(encoding="utf-8").split('id="urgent-deadlines"', 1)[1].split("</section>", 1)[0]

            self.assertEqual(public_urgent.count('class="urgent-item '), 4)
            self.assertEqual(internal_urgent.count('class="urgent-item '), 4)
            for title in ("온실가스 D-7 컨설팅", "온실가스 D-4 설비 지원", "온실가스 D-2 융자 지원", "배출권 D-DAY 컨설팅"):
                self.assertIn(title, public_urgent)
            for title in ("기후변화 D-1 영상 제작", "온실가스 D-8 컨설팅", "온실가스 오늘 마감 경과"):
                self.assertNotIn(title, public_urgent)
            self.assertIn('<span>마감 임박</span><strong>4</strong>', rendered)
            self.assertIn('data-deadline-group="yellow"', rendered)
            self.assertIn('data-deadline-group="red"', rendered)
            self.assertIn('data-deadline-group="deep-red"', rendered)
            self.assertIn('value="urgent">Tier 1·2 D-7 이내', rendered)
            self.assertIn('class="urgent-item urgent-deep-red"', public_urgent)
            self.assertIn('background:#7F1D1D;color:#FFFFFF;">D-DAY', public_urgent)

            rows = {str(row["external_id"]): notice_view(row, NOW) for row in list_notices(connection)}
            self.assertEqual(rows["day-0"]["deadline_priority"], "D-DAY")
            self.assertFalse(rows["closed-today"]["is_active"])
            self.assertEqual(rows["closed-today"]["deadline_priority"], "")
            connection.close()

    def test_weekly_urgent_section_and_daily_badges_use_same_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            connection = connect(Path(directory) / "tracker.db")
            seed_notices(connection)
            initialize_baseline(connection, NOW - timedelta(days=1))
            sent = []
            result = dispatch_notifications(
                connection,
                recipients=["test@example.com"],
                mode="weekly",
                send=True,
                sender=lambda _recipient, payload: sent.append(payload),
                now=NOW,
            )
            self.assertEqual(result[0].sent, 1)
            section = sent[0].text.split("[마감 임박 · Tier 1/2 · D-7 이내]", 1)[1].split("\n\n", 1)[0]
            self.assertIn("온실가스 D-7 컨설팅", section)
            self.assertIn("온실가스 D-2 융자 지원", section)
            self.assertIn("배출권 D-DAY 컨설팅", section)
            self.assertNotIn("기후변화 D-1 영상 제작", section)
            self.assertNotIn("온실가스 D-8 컨설팅", section)
            self.assertNotIn("D-7 / D-3 중요 마감", sent[0].html)
            self.assertIn("마감 임박 · Tier 1/2", sent[0].html)
            self.assertIn("background:#7F1D1D;color:#FFFFFF", _email_deadline_badge("D-DAY"))
            self.assertIn("color:#8A2A26", _email_deadline_badge("D-2"))
            self.assertIn("color:#7B5510", _email_deadline_badge("D-6"))
            connection.close()


if __name__ == "__main__":
    unittest.main()
