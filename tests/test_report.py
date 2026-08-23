import json
import unittest
from datetime import date

from assistout.report import countdown_line, days_left, render_json, totals
from assistout.scanner import Finding


def mk(line=1, col=1, category="runs", effort="manual", path="a.py", match="m"):
    return Finding(
        path=path,
        line=line,
        col=col,
        category=category,
        effort=effort,
        match=match,
        replacement="r",
        note="n",
    )


class DaysLeftTests(unittest.TestCase):
    def test_three_days_before(self):
        self.assertEqual(days_left(date(2026, 8, 23)), 3)

    def test_final_day(self):
        self.assertEqual(days_left(date(2026, 8, 25)), 1)

    def test_shutdown_day_is_zero(self):
        self.assertEqual(days_left(date(2026, 8, 26)), 0)

    def test_negative_after(self):
        self.assertEqual(days_left(date(2026, 9, 2)), -7)


class CountdownLineTests(unittest.TestCase):
    def test_days_left(self):
        self.assertIn("3 days left", countdown_line(date(2026, 8, 23)))

    def test_final_day(self):
        self.assertIn("final day", countdown_line(date(2026, 8, 25)))

    def test_today(self):
        self.assertIn("TODAY", countdown_line(date(2026, 8, 26)))

    def test_after_shutdown(self):
        line = countdown_line(date(2026, 9, 2))
        self.assertIn("migration is mandatory", line)
        self.assertIn("7 days ago", line)


class TotalsTests(unittest.TestCase):
    def test_grouping_and_order(self):
        findings = [
            mk(category="runs"),
            mk(category="runs"),
            mk(category="thread_crud"),
            mk(category="thread_messages", effort="moderate"),
        ]
        t = totals(findings)
        self.assertEqual(t["findings"], 4)
        self.assertEqual(
            t["by_category"], {"runs": 2, "thread_crud": 1, "thread_messages": 1}
        )
        self.assertEqual(t["by_effort"], {"manual": 3, "moderate": 1})


class RenderJsonTests(unittest.TestCase):
    def test_schema_and_grouping(self):
        findings = [mk(path="a.py"), mk(path="a.py", line=2), mk(path="b/c.js")]
        payload = json.loads(
            json.dumps(render_json("root", findings, 9, today=date(2026, 8, 23)))
        )
        self.assertEqual(payload["tool"], "assistout")
        self.assertEqual(payload["shutdown_date"], "2026-08-26")
        self.assertEqual(payload["days_left"], 3)
        self.assertEqual(payload["files_scanned"], 9)
        self.assertEqual([f["path"] for f in payload["files"]], ["a.py", "b/c.js"])
        self.assertEqual(len(payload["files"][0]["findings"]), 2)
        self.assertEqual(payload["totals"]["findings"], 3)

    def test_empty_findings(self):
        payload = render_json("root", [], 0, today=date(2026, 8, 23))
        self.assertEqual(payload["files"], [])
        self.assertEqual(payload["totals"]["by_category"], {})


if __name__ == "__main__":
    unittest.main()
