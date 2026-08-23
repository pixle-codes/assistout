import contextlib
import io
import json
import os
import sys
import tempfile
import types
import unittest

from assistout.backfill import generate_script


def _fake_openai(pages_by_thread, created):
    """Build a fake `openai` module recording conversations.create calls."""
    mod = types.ModuleType("openai")

    class FakePart:
        def __init__(self, type, **kw):
            self.type = type
            self.__dict__.update(kw)

    class FakeText:
        def __init__(self, value):
            self.value = value

    class FakeMessage:
        def __init__(self, mid, role, parts):
            self.id = mid
            self.role = role
            self.content = parts

        @staticmethod
        def text(mid, role, value):
            return FakeMessage(mid, role, [FakePart("text", text=FakeText(value))])

    class FakePage:
        def __init__(self, data):
            self.data = data

    class FakePager:
        def __init__(self, data):
            self._data = data

        def iter_pages(self):
            yield FakePage(self._data[:2])
            if len(self._data) > 2:
                yield FakePage(self._data[2:])

    class FakeMessages:
        def list(self, thread_id, order=None, limit=None):
            assert order == "asc"
            return FakePager(pages_by_thread[thread_id])

    class FakeConversations:
        def create(self, items=None, metadata=None):
            cid = f"conv_{len(created) + 1:03d}"
            created.append({"id": cid, "items": items, "metadata": metadata})
            return types.SimpleNamespace(id=cid)

    class FakeBeta:
        threads = None

    beta = FakeBeta()
    beta.threads = types.SimpleNamespace(messages=FakeMessages())

    class FakeClient:
        def __init__(self, *a, **kw):
            self.beta = beta
            self.conversations = FakeConversations()

    mod.OpenAI = FakeClient
    mod.FakeMessage = FakeMessage
    return mod


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.src = generate_script()

    def test_compiles(self):
        compile(self.src, "backfill_conversations.py", "exec")

    def test_official_recipe_calls_present(self):
        for needle in (
            'threads.messages.list(',
            'order="asc"',
            ".iter_pages()",
            "conversations.create(items=items",
            '"input_text" if message.role == "user"',
            '"output_text"',
            '"input_image"',
            '"legacy_thread_id"',
        ):
            self.assertIn(needle, self.src)

    def test_parameterization_and_policy(self):
        for needle in (
            "ASSISTOUT_THREAD_IDS",
            "--dry-run",
            "--allow-lossy",
            "--map",
            "backfill_map.jsonl",
            "2026-08-26",
        ):
            self.assertIn(needle, self.src)

    def test_no_third_party_deps_beyond_openai(self):
        imports = [
            line.split()[1]
            for line in self.src.splitlines()
            if line.startswith("import ") or line.startswith("from ")
        ]
        allowed = {"argparse", "json", "os", "sys", "openai"}
        tops = {name.split(".")[0] for name in imports}
        froms = {
            line.split()[1]
            for line in self.src.splitlines()
            if line.startswith("from ")
        }
        self.assertTrue(tops <= allowed | froms)


class EmittedScriptTests(unittest.TestCase):
    """Exec the generated script against a fake SDK; no network, no deps."""

    def setUp(self):
        self.src = generate_script()
        self._tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self._tmp.name)
        self.created = []

    def tearDown(self):
        os.chdir(self.cwd)
        self._tmp.cleanup()

    def run_script(self, argv, pages):
        sys.modules["openai"] = _fake_openai(pages, self.created)
        code_out, err_out = io.StringIO(), io.StringIO()
        old_argv = sys.argv
        sys.argv = ["backfill_conversations.py"] + argv
        try:
            g = {"__name__": "__main__", "__file__": "bf.py"}
            with contextlib.redirect_stdout(code_out), contextlib.redirect_stderr(err_out):
                try:
                    exec(compile(self.src, "bf.py", "exec"), g)
                    exit_code = 0
                except SystemExit as e:
                    exit_code = e.code if isinstance(e.code, int) else 0
        finally:
            sys.argv = old_argv
            del sys.modules["openai"]
        return exit_code, code_out.getvalue(), err_out.getvalue()

    def msgs(self, n=3):
        return [
            {"id": f"m{i}", "role": "user" if i % 2 == 0 else "assistant"}
            for i in range(n)
        ]

    def fake_pages(self, thread_id, n=3, extra_part=None):
        mod = _fake_openai({}, self.created)
        fm = mod.FakeMessage
        out = []
        for i in range(n):
            role = "user" if i % 2 == 0 else "assistant"
            if extra_part is not None and i == 1:
                out.append(fm(f"{thread_id}-m{i}", role, [extra_part]))
            else:
                out.append(
                    fm.text(
                        f"{thread_id}-m{i}",
                        role,
                        f"hello {i}",
                    )
                )
        return out

    def test_happy_path_creates_conversation_and_journal(self):
        pages = {
            "thr_A": self.fake_pages("thr_A", 3),
            "thr_B": self.fake_pages("thr_B", 2),
        }
        code, out, err = self.run_script(["thr_A", "thr_B"], pages)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.created), 2)
        first = self.created[0]
        self.assertEqual(first["metadata"]["legacy_thread_id"], "thr_A")
        roles = [i["role"] for i in first["items"]]
        self.assertEqual(roles, ["user", "assistant", "user"])
        self.assertEqual(first["items"][0]["content"][0]["type"], "input_text")
        self.assertEqual(first["items"][1]["content"][0]["type"], "output_text")
        with open("backfill_map.jsonl", encoding="utf-8") as fh:
            lines = fh.read().strip().splitlines()
        self.assertEqual(lines[0].split("\t")[0], "thr_A")
        self.assertEqual(lines[1].split("\t")[0], "thr_B")

    def test_rerun_skips_mapped_threads(self):
        pages = {"thr_A": self.fake_pages("thr_A", 2)}
        code, _, _ = self.run_script(["thr_A"], pages)
        self.assertEqual(code, 0)
        code, out, _ = self.run_script(["thr_A"], pages)
        self.assertEqual(code, 0)
        self.assertIn("already mapped", out)
        self.assertEqual(len(self.created), 1)

    def test_dry_run_creates_nothing(self):
        pages = {"thr_A": self.fake_pages("thr_A", 4)}
        code, out, _ = self.run_script(["thr_A", "--dry-run"], pages)
        self.assertEqual(code, 0)
        self.assertEqual(self.created, [])
        self.assertIn("dry-run thr_A: 4+ message(s)", out)
        self.assertFalse(os.path.exists("backfill_map.jsonl"))

    def test_unsupported_content_fails_visible_then_lossy_succeeds(self):
        bad_part = {"type": "image_file"}
        pages = {
            "thr_bad": self.fake_pages("thr_bad", 2, extra_part=bad_part),
        }
        # Rebuild with a real FakePart-like object carrying attributes.
        mod = _fake_openai({}, self.created)

        class P:
            pass

        part = P()
        part.type = "image_file"
        pages = {"thr_bad": []}
        fm = mod.FakeMessage
        pages["thr_bad"] = [
            fm.text("m0", "user", "hi"),
            fm("m1", "assistant", [part]),
        ]
        code, _, err = self.run_script(["thr_bad"], pages)
        self.assertEqual(code, 1)
        self.assertEqual(self.created, [])
        self.assertIn("unsupported content part(s)", err)
        self.assertIn("--allow-lossy", err)
        # Now allow lossy drops: succeeds, records what was lost.
        code, out, err = self.run_script(["thr_bad", "--allow-lossy"], pages)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.created), 1)
        self.assertIn("dropped parts: ['image_file']", out)

    def test_env_var_ids(self):
        pages = {"thr_ENV": self.fake_pages("thr_ENV", 2)}
        old = os.environ.get("ASSISTOUT_THREAD_IDS")
        os.environ["ASSISTOUT_THREAD_IDS"] = "thr_ENV"
        try:
            code, _, _ = self.run_script([], pages)
        finally:
            if old is None:
                del os.environ["ASSISTOUT_THREAD_IDS"]
            else:
                os.environ["ASSISTOUT_THREAD_IDS"] = old
        self.assertEqual(code, 0)
        self.assertEqual(len(self.created), 1)

    def test_custom_metadata_flag(self):
        pages = {"thr_M": self.fake_pages("thr_M", 2)}
        code, _, _ = self.run_script(["thr_M", "--metadata", "team=core"], pages)
        self.assertEqual(code, 0)
        self.assertEqual(self.created[0]["metadata"]["team"], "core")
        self.assertEqual(self.created[0]["metadata"]["legacy_thread_id"], "thr_M")


if __name__ == "__main__":
    unittest.main()
