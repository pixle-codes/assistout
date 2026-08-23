import os
import tempfile
import unittest

from assistout.scanner import is_binary, iter_files, scan_path, scan_text


class ScanTextTests(unittest.TestCase):
    def test_run_steps_beats_generic_runs(self):
        hits = scan_text("client.beta.threads.runs.steps.list(thread_id=t, run_id=r)")
        self.assertEqual([h["category"] for h in hits], ["run_steps"])

    def test_stream_beats_generic_runs(self):
        hits = scan_text("client.beta.threads.runs.stream(assistant_id=a)")
        self.assertEqual([h["category"] for h in hits], ["streaming", "assistant_id_arg"])

    def test_assistant_id_kwarg_flagged_in_python(self):
        hits = scan_text(
            "run = client.beta.threads.runs.create(thread_id=t, assistant_id='asst_x')"
        )
        cats = [h["category"] for h in hits]
        self.assertEqual(cats, ["runs", "assistant_id_arg"])

    def test_js_run_helpers_flagged(self):
        for call in ("createAndPoll", "createAndStream"):
            code = f"const run = await client.beta.threads.runs.{call}(thread.id, {{assistant_id: a}});"
            hits = scan_text(code)
            cats = {h["category"] for h in hits}
            self.assertIn("js_run_helpers", cats, call)
            self.assertIn("assistant_id_arg", cats, call)

    def test_read_attribute_not_flagged_as_arg(self):
        self.assertEqual(scan_text("console.log(run.assistant_id)"), [])
        self.assertEqual(scan_text("print(run.assistant_id)"), [])

    def test_poll_classified_as_runs(self):
        hits = scan_text("client.beta.threads.runs.poll(run_id=r)")
        self.assertEqual([h["category"] for h in hits], ["runs"])

    def test_overlapping_calls_both_reported(self):
        line = 'client.beta.threads.messages.create(thread_id="t"); client.beta.threads.runs.retrieve(run_id="r")'
        cats = {h["category"] for h in scan_text(line)}
        self.assertEqual(cats, {"thread_messages", "runs"})

    def test_event_handler_import_flagged_as_streaming(self):
        hits = scan_text("from openai.helpers import AssistantEventHandler")
        self.assertEqual(hits[0]["category"], "streaming")
        self.assertEqual(hits[0]["line"], 1)

    def test_line_numbers_are_one_based(self):
        text = "\n\nclient.beta.threads.delete(thread_id='t')\n"
        hits = scan_text(text)
        self.assertEqual(hits[0]["line"], 3)

    def test_clean_responses_code_has_no_findings(self):
        code = (
            "client.responses.create(model='m', input='hi', "
            "conversation=conv_id)"
        )
        self.assertEqual(scan_text(code), [])


class IsBinaryTests(unittest.TestCase):
    def test_nul_byte_detected(self):
        self.assertTrue(is_binary(b"abc\x00def"))

    def test_text_not_detected(self):
        self.assertFalse(is_binary(b"plain text" * 1000))


class ScanPathTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, content, mode="w"):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path) or self.root, exist_ok=True)
        with open(path, mode) as fh:
            fh.write(content)
        return path

    def test_python_rules_apply_to_py_only(self):
        self.write("app.py", "client.beta.threads.create()\n")
        self.write("doc.md", "docs say use client.beta.threads.create()\n")
        _, findings = scan_path(self.root)
        self.assertEqual(
            [(os.path.basename(f.path), f.category) for f in findings],
            [("app.py", "thread_crud")],
        )

    def test_any_file_rules_hit_other_languages(self):
        self.write('svc.ts', 'fetch("/v1/threads/" + id)\n')
        _, findings = scan_path(self.root)
        self.assertEqual(findings[0].category, "http_endpoints")

    def test_js_sdk_calls_flagged_in_ts(self):
        self.write(
            "agent.ts",
            "const run = await client.beta.threads.runs.createAndPoll(thread.id, {\n"
            "  assistant_id: 'asst_abc123456',\n"
            "});\n"
            "const msgs = await client.beta.threads.messages.list(thread.id);\n",
        )
        _, findings = scan_path(self.root)
        cats = [f.category for f in findings]
        self.assertEqual(
            cats,
            [
                "js_run_helpers",
                "assistant_id_arg",
                "assistant_refs",
                "thread_messages",
            ],
        )

    def test_js_rules_do_not_leak_into_python_or_md(self):
        js_code = "client.beta.threads.runs.createAndPoll(t, a)\n"
        self.write("a.js", js_code)
        self.write("b.py", "pass\n")
        self.write("c.md", "docs mention createAndPoll here\n")
        _, findings = scan_path(self.root)
        by_file = {os.path.basename(f.path): f.category for f in findings}
        self.assertEqual(by_file, {"a.js": "js_run_helpers"})

    def test_node_modules_skipped(self):
        self.write("node_modules/pkg/index.py", "client.beta.threads.create()\n")
        scanned, findings = scan_path(self.root)
        self.assertEqual((scanned, len(findings)), (0, 0))

    def test_binary_file_skipped(self):
        self.write("blob.py", b"asst_123456789\x00\x01binary", mode="wb")
        scanned, findings = scan_path(self.root)
        self.assertEqual((scanned, len(findings)), (0, 0))

    def test_single_file_path(self):
        path = self.write("one.py", "client.beta.threads.create()\n")
        scanned, findings = scan_path(path)
        self.assertEqual(scanned, 1)
        self.assertEqual(findings[0].path, os.path.normpath(path))

    def test_findings_sorted_by_line(self):
        self.write(
            "z.py",
            "client.beta.threads.runs.retrieve(run_id='a')\n"
            "client.beta.threads.create()\n",
        )
        _, findings = scan_path(self.root)
        self.assertEqual([f.line for f in findings], [1, 2])

    def test_missing_root_yields_nothing(self):
        scanned, findings = scan_path(os.path.join(self.root, "nope"))
        self.assertEqual((scanned, findings), (0, []))

    def test_iter_files_is_generator(self):
        import types

        self.assertIsInstance(iter_files(self.root), types.GeneratorType)


if __name__ == "__main__":
    unittest.main()
