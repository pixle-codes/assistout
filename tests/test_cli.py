import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import date

from assistout.cli import main


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        with open(os.path.join(self.root, "app.py"), "w") as fh:
            fh.write("client.beta.threads.create()\n")

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_findings_exit_1(self):
        code, out, _ = self.run_cli([self.root])
        self.assertEqual(code, 1)
        self.assertIn("thread_crud", out)

    def test_clean_tree_exits_0(self):
        os.remove(os.path.join(self.root, "app.py"))
        with open(os.path.join(self.root, "ok.py"), "w") as fh:
            fh.write("print('hi')\n")
        code, out, _ = self.run_cli([self.root])
        self.assertEqual(code, 0)
        self.assertIn("No Assistants API usage found", out)

    def test_json_output_shape(self):
        code, out, _ = self.run_cli(["--json", self.root])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        expected_days = (date(2026, 8, 26) - date.today()).days
        self.assertEqual(payload["days_left"], expected_days)
        self.assertEqual(payload["totals"]["findings"], 1)
        self.assertEqual(
            payload["files"][0]["findings"][0]["category"], "thread_crud"
        )

    def test_missing_path_exits_2(self):
        code, _, err = self.run_cli([os.path.join(self.root, "gone")])
        self.assertEqual(code, 2)
        self.assertIn("no readable files", err)

    def test_single_file_target(self):
        code, out, _ = self.run_cli([os.path.join(self.root, "app.py")])
        self.assertEqual(code, 1)
        self.assertIn("L1", out)

    def test_emit_backfill_writes_file(self):
        out_path = os.path.join(self.root, "backfill_conversations.py")
        code, out, _ = self.run_cli(["--emit-backfill", out_path])
        self.assertEqual(code, 0)
        self.assertIn("wrote", out)
        with open(out_path, encoding="utf-8") as fh:
            src = fh.read()
        compile(src, out_path, "exec")
        self.assertIn("threads.messages.list(", src)

    def test_emit_backfill_refuses_overwrite_without_force(self):
        out_path = os.path.join(self.root, "bf.py")
        code, _, _ = self.run_cli(["--emit-backfill", out_path])
        self.assertEqual(code, 0)
        code, _, err = self.run_cli(["--emit-backfill", out_path])
        self.assertEqual(code, 2)
        self.assertIn("--force", err)
        code, _, _ = self.run_cli(["--emit-backfill", out_path, "--force"])
        self.assertEqual(code, 0)

    def test_emit_backfill_stdout(self):
        code, out, _ = self.run_cli(["--emit-backfill", "-"])
        self.assertEqual(code, 0)
        self.assertIn("conversations.create(items=items", out)

    def test_sarif_writes_file_and_keeps_human_report(self):
        out_path = os.path.join(self.root, "findings.sarif")
        code, out, _ = self.run_cli(["--sarif", out_path, self.root])
        self.assertEqual(code, 1)
        self.assertIn("thread_crud", out)
        with open(out_path, encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertEqual(doc["version"], "2.1.0")
        results = doc["runs"][0]["results"]
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["ruleId"].startswith("assistout/"))
        uri = results[0]["locations"][0]["physicalLocation"]["artifactLocation"][
            "uri"
        ]
        self.assertFalse(os.path.isabs(uri))

    def test_sarif_stdout_is_pure_sarif(self):
        code, out, _ = self.run_cli(["--sarif", "-", self.root])
        self.assertEqual(code, 1)
        doc = json.loads(out)
        self.assertEqual(doc["runs"][0]["results"][0]["ruleId"], "assistout/thread_crud")
        self.assertNotIn("assistout v", out.split('"$schema"')[0])

    def test_sarif_clean_tree_gives_empty_results_exit_0(self):
        os.remove(os.path.join(self.root, "app.py"))
        with open(os.path.join(self.root, "ok.py"), "w") as fh:
            fh.write("print('hi')\n")
        code, out, _ = self.run_cli(
            ["--sarif", os.path.join(self.root, "o.sarif"), self.root]
        )
        self.assertEqual(code, 0)
        with open(os.path.join(self.root, "o.sarif"), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertEqual(doc["runs"][0]["results"], [])

    def test_sarif_unwritable_target_exits_2(self):
        bad = os.path.join(self.root, "no-such-dir", "out.sarif")
        code, _, err = self.run_cli(["--sarif", bad, self.root])
        self.assertEqual(code, 2)
        self.assertIn("cannot write", err)


if __name__ == "__main__":
    unittest.main()
