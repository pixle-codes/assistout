"""Detection rules mapping OpenAI Assistants API usage to Responses/Conversations replacements."""

import re
from dataclasses import dataclass, field
from datetime import date

SHUTDOWN_DATE = date(2026, 8, 26)

PYTHON_TARGETS = {".py"}
JS_TARGETS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
PY = "py"
JS = "js"
ANY_FILE = "any"


@dataclass
class Rule:
    category: str
    effort: str
    pattern: str
    replacement: str
    note: str
    targets: tuple = (PY,)

    def __post_init__(self):
        self.compiled_pattern = re.compile(self.pattern)
        self.targets = tuple(self.targets)

    def compiled(self):
        return self.compiled_pattern


def rules_for(ext: str):
    """Rules applicable to a file extension; explicit pass-through (s10 lesson)."""
    if ext in PYTHON_TARGETS:
        langs = {PY}
    elif ext in JS_TARGETS:
        langs = {JS}
    else:
        return [r for r in RULES if r.targets == (ANY_FILE,)]
    return [
        r for r in RULES if r.targets == (ANY_FILE,) or langs.intersection(r.targets)
    ]


RULES = [
    Rule(
        category="run_steps",
        effort="manual",
        pattern=r"\.beta\.threads\s*\.\s*runs\s*\.\s*steps\s*\.",
        replacement="response.output[] items",
        note=(
            "Run steps are gone; iterate the Response object's output[] items "
            "(messages, tool calls, outputs) instead."
        ),
        targets=(PY, JS),
    ),
    Rule(
        category="streaming",
        effort="manual",
        pattern=r"\bAssistantEventHandler\b|\bAssistantStreamManager\b|\.beta\.threads\s*\.\s*runs\s*\.\s*stream\b",
        replacement="responses.stream(...) events",
        note=(
            "Assistants streaming helpers no longer exist; use Responses "
            "streaming events (e.g. response.output_text.delta) or "
            "background=True + retrieve."
        ),
        targets=(PY, JS),
    ),
    Rule(
        category="js_run_helpers",
        effort="manual",
        pattern=r"\.\s*createAnd(?:Poll|Stream)\b",
        replacement="await client.responses.create(...) / responses.stream(...)",
        note=(
            "JS SDK convenience helpers (createAndPoll/createAndStream) are "
            "gone with the Assistants API; a single awaited responses.create "
            "replaces create-and-poll, and Responses streaming events replace "
            "createAndStream."
        ),
        targets=(JS,),
    ),
    Rule(
        category="runs",
        effort="manual",
        pattern=r"\.beta\.threads\s*\.\s*runs\s*\.\s*\w+",
        replacement="client.responses.create(conversation=..., input=[...])",
        note=(
            "Runs become Responses: send input items, get output items back. "
            "Delete polling loops - responses.create is synchronous (or "
            "background=True with retrieval). Tool-call loops are explicit now."
        ),
        targets=(PY, JS),
    ),
    Rule(
        category="thread_messages",
        effort="moderate",
        pattern=r"\.beta\.threads\s*\.\s*messages\s*\.\s*\w+",
        replacement="conversations.items (+ official backfill recipe)",
        note=(
            "Thread messages become conversation items. For one-time backfill, "
            "the official recipe pages threads.messages.list(order='asc') into "
            "conversations.create(items=...) - do it before shutdown."
        ),
        targets=(PY, JS),
    ),
    Rule(
        category="thread_crud",
        effort="mechanical",
        pattern=r"\.beta\.threads\s*\.\s*(create|retrieve|update|delete)\b",
        replacement="client.conversations.create/retrieve/update/delete",
        note=(
            "Threads map to Conversations almost 1:1; item ids move from "
            "thread_* to conv_*. Conversations store arbitrary items, not just "
            "messages."
        ),
        targets=(PY, JS),
    ),
    Rule(
        category="assistant_objects",
        effort="manual",
        pattern=r"\.beta\.assistants\s*\.",
        replacement="dashboard Prompts: prompt={'id': ...}",
        note=(
            "Recreate each assistant bundle (model+instructions+tools) as a "
            "named Prompt in the dashboard and pass prompt={'id': ...} to "
            "responses.create. Caution: reusable prompts carry their own "
            "deprecation timeline - prefer versioned prompt objects."
        ),
        targets=(PY, JS),
    ),
    Rule(
        category="vector_stores",
        effort="moderate",
        pattern=r"\.beta\.vector_stores\s*\.",
        replacement="tools=[{'type': 'file_search', 'vector_store_ids': [...]}]",
        note=(
            "Vector stores themselves survive under Responses, but attachment "
            "moves from assistant tool_resources to a file_search tool on "
            "responses.create."
        ),
        targets=(PY, JS),
    ),
    Rule(
        category="assistant_id_arg",
        effort="moderate",
        pattern=r"\bassistant_?[iI]d\b\s*[:=]",
        replacement="prompt={'id': ...} on responses.create",
        note=(
            "Call site passes an assistant id; recreate the assistant bundle "
            "as a dashboard Prompt and pass prompt={'id': ...} instead."
        ),
        targets=(PY, JS),
    ),
    Rule(
        category="assistant_refs",
        effort="moderate",
        pattern=r"\basst_[A-Za-z0-9]{8,}\b",
        replacement="dashboard prompt id via prompt={'id': ...}",
        note="Hardcoded assistant id; swap for a dashboard prompt id after recreating the bundle.",
        targets=(ANY_FILE,),
    ),
    Rule(
        category="assistant_refs",
        effort="moderate",
        pattern=r"\bOPENAI_ASSISTANT_ID\b",
        replacement="dashboard prompt id via prompt={'id': ...}",
        note=(
            "Config references an assistant id; replace with a prompt id once "
            "the assistant is recreated as a Prompt."
        ),
        targets=(ANY_FILE,),
    ),
    Rule(
        category="http_endpoints",
        effort="manual",
        pattern=r"/v1/threads\b|/v1/assistants\b",
        replacement="/v1/conversations + /v1/responses",
        note=(
            "Raw REST calls to /v1/threads* and /v1/assistants* stop working "
            "at shutdown; port to /v1/conversations (state) and /v1/responses "
            "(execution)."
        ),
        targets=(ANY_FILE,),
    ),
]
