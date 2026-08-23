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


if __name__ == "__main__":
    unittest.main()
