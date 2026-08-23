import json
import unittest
from datetime import date

from assistout.report import (
    countdown_line,
    days_left,
    render_human,
    render_json,
    totals,
)
from assistout.scanner import Finding


def mk(
    line=1,
    col=1,
    category="runs",
    effort="manual",
    path="a.py",
    match="m",
    hint_before="",
    hint_after="",
):
    return Finding(
        path=path,
        line=line,
        col=col,
        category=category,
        effort=effort,
        match=match,
        replacement="r",
        note="n",
        hint_before=hint_before,
        hint_after=hint_after,
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

    def test_hints_included(self):
        payload = render_json(
            "root",
            [mk(hint_before="b", hint_after="a")],
            1,
            today=date(2026, 8, 23),
        )
        finding = payload["files"][0]["findings"][0]
        self.assertEqual(finding["hint_before"], "b")
        self.assertEqual(finding["hint_after"], "a")


class RenderHumanHintTests(unittest.TestCase):
    def test_hint_lines_shown(self):
        out = render_human([mk(hint_before="old()", hint_after="new()")], 1)
        self.assertIn("- old()", out)
        self.assertIn("+ new()", out)

    def test_no_hint_lines_when_empty(self):
        out = render_human([mk()], 1)
        self.assertNotIn("        - ", out)
        self.assertNotIn("        + ", out)

    def test_identical_consecutive_hints_deduped(self):
        findings = [
            mk(line=1, hint_before="old", hint_after="new"),
            mk(line=2, hint_before="old", hint_after="new"),
            mk(line=3, category="thread_crud", hint_before="o2", hint_after="n2"),
            mk(line=4, hint_before="old", hint_after="new"),
        ]
        out = render_human(findings, 1)
        self.assertEqual(out.count("- old"), 2)
        self.assertEqual(out.count("- o2"), 1)

    def test_new_file_resets_dedupe(self):
        findings = [
            mk(path="a.py", line=1, hint_before="old", hint_after="new"),
            mk(path="b.py", line=1, hint_before="old", hint_after="new"),
        ]
        out = render_human(findings, 1)
        self.assertEqual(out.count("- old"), 2)


if __name__ == "__main__":
    unittest.main()
