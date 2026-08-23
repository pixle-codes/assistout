import tempfile
import unittest

from assistout.knowledge import AGENTS_CLASSIC_DATE
from assistout.report import classic_agents_line, render_human, render_json
from assistout.sarif import render_sarif
from assistout.scanner import scan_path, scan_text

FOUNDRY_PY = """\
from azure.ai.projects import AIProjectClient

agent = project_client.agents.create_agent(
    model="gpt-4.1", name="my-agent", instructions=inst,
)
thread = project_client.agents.threads.create()
message = project_client.agents.messages.create(
    thread_id=thread.id, role="user", content="hi",
)
run = project_client.agents.runs.create_and_process(thread_id=thread.id)
run2 = project_client.agents.runs.get(thread_id=thread.id, run_id=run.id)
"""

NEW_FOUNDRY_PY = """\
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition

project = AIProjectClient(endpoint=EP, credential=cred)
openai = project.get_openai_client()
agent = project.agents.create_version(
    agent_name="my-agent",
    definition=PromptAgentDefinition(model="gpt-4.1", instructions=inst),
)
conv = openai.conversations.create(items=items)
res = openai.responses.create(conversation=conv.id, input="hi")
"""

FOUNDRY_JS = """\
const agent = await client.agents.createAgent("gpt-4.1", {name: "a"});
const thread = await client.agents.createThread({messages});
await client.agents.createMessage(thread.id, {role: "user", content});
const msgs = await client.agents.listMessages(thread.id);
let run = await client.agents.createRun(threadId, agentId);
run = await client.agents.getRun(threadId, run.id);
"""

AZURE_HTTP_TF = """\
resource "null_resource" "probe" {
  provisioner "local-exec" {
    command = "curl -X POST https://myres.openai.azure.com/openai/threads?api-version=2024-02-15-preview -H 'api-key: KEY'"
  }
}
"""


def _scan_tree(files):
    with tempfile.TemporaryDirectory() as td:
        for name, content in files.items():
            with open(f"{td}/{name}", "w", encoding="utf-8") as fh:
                fh.write(content)
        return scan_path(td)


class FoundryPythonTests(unittest.TestCase):
    def test_all_classic_shapes_flagged(self):
        scanned, findings = _scan_tree({"agent.py": FOUNDRY_PY})
        self.assertEqual(scanned, 1)
        cats = {f.category for f in findings}
        self.assertEqual(
            cats,
            {
                "foundry_create_agent",
                "foundry_threads",
                "foundry_messages",
                "foundry_run_process",
                "foundry_runs",
            },
        )

    def test_create_and_process_wins_over_generic_runs(self):
        hits = scan_text("client.agents.runs.create_and_process(thread_id=t)")
        self.assertEqual([h["category"] for h in hits], ["foundry_run_process"])

    def test_deadline_is_classic_retirement(self):
        _, findings = _scan_tree({"agent.py": FOUNDRY_PY})
        for f in findings:
            self.assertEqual(f.deadline, AGENTS_CLASSIC_DATE.isoformat())

    def test_new_sdk_style_code_not_flagged(self):
        _, findings = _scan_tree({"new.py": NEW_FOUNDRY_PY})
        self.assertEqual(findings, [])


class FoundryJsTests(unittest.TestCase):
    def test_js_shapes_flagged(self):
        _, findings = _scan_tree({"agent.js": FOUNDRY_JS})
        cats = {f.category for f in findings}
        self.assertEqual(cats, {"foundry_create_agent", "foundry_threads", "foundry_messages", "foundry_runs"})

    def test_js_deadline(self):
        _, findings = _scan_tree({"agent.js": FOUNDRY_JS})
        self.assertTrue(findings)
        for f in findings:
            self.assertEqual(f.deadline, "2027-03-31")


class AzureHttpTests(unittest.TestCase):
    def test_azure_threads_endpoint_in_terraform(self):
        _, findings = _scan_tree({"main.tf": AZURE_HTTP_TF})
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f.category, "azure_http_endpoints")
        # Azure Assistants HTTP dies on the SAME day as OpenAI's.
        self.assertEqual(f.deadline, "2026-08-26")

    def test_openai_v1_paths_unaffected_by_azure_rule(self):
        hits = scan_text("https://api.openai.com/v1/conversations")
        self.assertEqual(hits, [])


class ReportTests(unittest.TestCase):
    def _mixed(self):
        return _scan_tree(
            {"a.py": FOUNDRY_PY, "b.py": "client.beta.threads.create()"}
        )

    def test_human_report_shows_both_deadline_lines(self):
        _, findings = self._mixed()
        out = render_human(findings, 2)
        self.assertIn("OpenAI Assistants API shuts down 2026-08-26 —", out)
        self.assertIn("Foundry Agent Service (classic) shuts down 2027-03-31 —", out)

    def test_human_report_single_line_without_foundry(self):
        with tempfile.TemporaryDirectory() as td:
            with open(f"{td}/x.py", "w", encoding="utf-8") as fh:
                fh.write("client.beta.threads.create()\n")
            _, findings = scan_path(td)
        out = render_human(findings, 1)
        self.assertNotIn("Foundry Agent Service (classic)", out)

    def test_json_carries_per_finding_deadlines(self):
        _, findings = self._mixed()
        payload = render_json(".", findings, 2)
        self.assertEqual(payload["agents_classic_retirement"], "2027-03-31")
        deadlines = {
            fd["deadline"]
            for page in payload["files"]
            for fd in page["findings"]
        }
        self.assertEqual(deadlines, {"2026-08-26", "2027-03-31"})


class SarifTests(unittest.TestCase):
    def test_foundry_rules_use_classic_date(self):
        _, findings = _scan_tree({"agent.py": FOUNDRY_PY})
        sarif = render_sarif(findings)
        rules = {r["id"]: r for r in sarif["runs"][0]["tool"]["driver"]["rules"]}
        rule = rules["assistout/foundry_runs"]
        self.assertIn("2027-03-31", rule["shortDescription"]["text"])
        self.assertEqual(rule["defaultConfiguration"]["level"], "error")

    def test_assistants_rule_text_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            with open(f"{td}/x.py", "w", encoding="utf-8") as fh:
                fh.write("client.beta.threads.create()\n")
            _, findings = scan_path(td)
        sarif = render_sarif(findings)
        rule = sarif["runs"][0]["tool"]["driver"]["rules"][0]
        self.assertEqual(
            rule["shortDescription"]["text"],
            "Assistants API usage (thread_crud) stops working "
            "at the 2026-08-26 shutdown",
        )


class CountdownTests(unittest.TestCase):
    def test_classic_line_far_future(self):
        from datetime import date

        line = classic_agents_line(date(2027, 3, 30))
        self.assertTrue(line.startswith("Foundry Agent Service (classic)"))
        self.assertIn("final day", line)


if __name__ == "__main__":
    unittest.main()
