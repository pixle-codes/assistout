import json
import unittest

from assistout.sarif import artifact_uri, fingerprint, level_for, render_sarif
from assistout.scanner import Finding


def mk(line=3, col=5, category="runs", effort="manual", path="src/app.py"):
    return Finding(
        path=path,
        line=line,
        col=col,
        category=category,
        effort=effort,
        match=".beta.threads.runs.create",
        replacement="responses.create",
        note="n",
        hint_before="before-snippet",
        hint_after="after-snippet",
    )


class LevelMappingTests(unittest.TestCase):
    def test_manual_is_error(self):
        self.assertEqual(level_for("manual"), "error")

    def test_moderate_is_warning(self):
        self.assertEqual(level_for("moderate"), "warning")

    def test_mechanical_is_note(self):
        self.assertEqual(level_for("mechanical"), "note")

    def test_unknown_effort_falls_back_to_warning(self):
        self.assertEqual(level_for("mystery"), "warning")


class ArtifactUriTests(unittest.TestCase):
    def test_forward_slashes_and_relative(self):
        import os

        target = os.path.join(os.getcwd(), "sub", "dir", "app.py")
        self.assertEqual(artifact_uri(target), "sub/dir/app.py")

    def test_already_relative_stays_intact(self):
        import os

        if os.path.isabs("x/y.py"):
            self.skipTest("platform uses absolute relative paths")
        self.assertEqual(artifact_uri("x/y.py"), "x/y.py")


class FingerprintTests(unittest.TestCase):
    def test_stable_for_same_inputs(self):
        a = fingerprint("runs", "a.py", 3, 5)
        b = fingerprint("runs", "a.py", 3, 5)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 40)

    def test_differs_on_location(self):
        a = fingerprint("runs", "a.py", 3, 5)
        b = fingerprint("runs", "a.py", 4, 5)
        self.assertNotEqual(a, b)


class RenderSarifTests(unittest.TestCase):
    def test_top_level_shape(self):
        doc = render_sarif([mk()])
        self.assertEqual(doc["version"], "2.1.0")
        self.assertIn("$schema", doc)
        self.assertEqual(len(doc["runs"]), 1)
        driver = doc["runs"][0]["tool"]["driver"]
        self.assertEqual(driver["name"], "assistout")
        self.assertIn("version", driver)

    def test_result_count_and_region(self):
        findings = [mk(), mk(line=9)]
        doc = render_sarif(findings)
        results = doc["runs"][0]["results"]
        self.assertEqual(len(results), 2)
        loc = results[0]["locations"][0]["physicalLocation"]
        self.assertEqual(loc["region"]["startLine"], 3)
        self.assertEqual(loc["region"]["startColumn"], 5)
        self.assertEqual(loc["artifactLocation"]["uri"], "src/app.py")

    def test_rules_deduped_per_category(self):
        findings = [
            mk(category="assistant_refs"),
            mk(category="assistant_refs", line=8),
            mk(category="thread_crud", effort="mechanical"),
        ]
        doc = render_sarif(findings)
        rules = doc["runs"][0]["tool"]["driver"]["rules"]
        ids = sorted(r["id"] for r in rules)
        self.assertEqual(ids, ["assistout/assistant_refs", "assistout/thread_crud"])

    def test_levels_flow_from_effort(self):
        findings = [
            mk(effort="manual"),
            mk(effort="moderate"),
            mk(effort="mechanical"),
        ]
        doc = render_sarif(findings)
        levels = {r["level"] for r in doc["runs"][0]["results"]}
        self.assertEqual(levels, {"error", "warning", "note"})

    def test_message_carries_hint(self):
        doc = render_sarif([mk()])
        text = doc["runs"][0]["results"][0]["message"]["text"]
        self.assertIn("before-snippet => after-snippet", text)

    def test_empty_findings_gives_valid_empty_doc(self):
        doc = render_sarif([])
        payload = json.loads(json.dumps(doc))
        self.assertEqual(payload["runs"][0]["results"], [])
        self.assertEqual(payload["runs"][0]["tool"]["driver"]["rules"], [])

    def test_partial_fingerprints_present(self):
        doc = render_sarif([mk()])
        fp = doc["runs"][0]["results"][0]["partialFingerprints"]
        key = "assistoutLocation/v1"
        self.assertIn(key, fp)
        self.assertEqual(
            fp[key], fingerprint("runs", "src/app.py", 3, 5)
        )

    def test_doc_is_json_serializable(self):
        json.dumps(render_sarif([mk(), mk(category="http_endpoints")]))


if __name__ == "__main__":
    unittest.main()
