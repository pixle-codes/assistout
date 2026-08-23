import os
import tempfile
import unittest
from datetime import date

from assistout.knowledge import RULES
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


class PromptObjectRuleTests(unittest.TestCase):
    """v1/prompts (reusable prompt objects) shut down 2026-11-30."""

    def test_pmpt_literal_flagged_in_any_file(self):
        hits = scan_text('PROMPT_ID = "pmpt_abc1234567"')
        self.assertEqual([h["category"] for h in hits], ["prompt_object_refs"])
        self.assertEqual(hits[0]["deadline"], "2026-11-30")

    def test_prompt_id_refs_flagged(self):
        for line in (
            'prompt_id = os.environ["OPENAI_PROMPT_ID"]',
            'promptId: "pmpt_1",',
            '{"prompt_id": pid}',
        ):
            cats = {h["category"] for h in scan_text(line)}
            self.assertIn("prompt_object_refs", cats, line)

    def test_sdk_prompts_calls_flagged(self):
        for lang, call in (
            ("py", 'client.prompts.retrieve("pmpt_123")'),
            ("py", "client.prompts.list()"),
            ("js", "await client.prompts.delete(pid)"),
        ):
            cats = {h["category"] for h in scan_text(call)}
            self.assertIn("prompt_sdk_calls", cats, call)

    def test_prompt_param_container_flagged_per_language(self):
        for line in (
            'client.responses.create(prompt={"prompt_id": pid})',
            'await client.responses.create({ prompt: { id: pid } });',
            'fetch(url, {body: JSON.stringify({"prompt": {...}})})',
        ):
            cats = {h["category"] for h in scan_text(line)}
            self.assertIn("prompt_param", cats, line)

    def test_v1_prompts_url_flagged_with_prompts_deadline(self):
        hits = scan_text("GET https://api.openai.com/v1/prompts/pmpt_123")
        cats = {h["category"] for h in hits}
        self.assertEqual(cats, {"http_endpoints", "prompt_object_refs"})
        deadlines = {h["deadline"] for h in hits}
        self.assertEqual(deadlines, {"2026-11-30"})

    def test_plain_prompt_word_not_flagged(self):
        for line in (
            "system_prompt = 'you are helpful'",
            'input="tell me a prompt joke"',
            "def run(prompt):",
            "improve_prompt(task)",
        ):
            self.assertEqual(scan_text(line), [], line)

    def test_realistic_migration_snippet_categories(self):
        code = (
            'pid = os.environ["OPENAI_PROMPT_ID"]\n'
            "res = client.responses.create(prompt={\"prompt_id\": pid, "
            '"version": "1"})\n'
        )
        cats = [h["category"] for h in scan_text(code)]
        self.assertEqual(cats[0], "prompt_object_refs")
        self.assertIn("prompt_param", cats)
        self.assertIn("prompt_object_refs", cats)

    def test_all_prompt_rules_carry_nov30_deadline(self):
        for rule in RULES:
            if rule.category.startswith("prompt_"):
                self.assertEqual(rule.deadline, date(2026, 11, 30), rule.category)

    def test_assistant_guidance_no_longer_points_at_pmpt(self):
        """s16: migrating into dashboard Prompts means a second migration."""
        for rule in RULES:
            if not rule.category.startswith("assistant"):
                continue
            blob = " ".join(
                [rule.replacement, rule.note, rule.hint_before, rule.hint_after]
            )
            self.assertNotIn("pmpt_", blob, rule.category)
            self.assertNotIn("prompt={'id'", blob, rule.category)


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
