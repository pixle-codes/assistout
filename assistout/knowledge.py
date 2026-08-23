"""Detection rules mapping OpenAI Assistants API usage to Responses/Conversations replacements."""

import re
from dataclasses import dataclass, field
from datetime import date

SHUTDOWN_DATE = date(2026, 8, 26)

PYTHON_TARGETS = {".py"}
ANY_FILE = "any"


@dataclass
class Rule:
    category: str
    effort: str
    pattern: str
    replacement: str
    note: str
    target: str = "python"

    def __post_init__(self):
        self.compiled_pattern = re.compile(self.pattern)

    def compiled(self):
        return self.compiled_pattern


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
    ),
    Rule(
        category="assistant_refs",
        effort="moderate",
        pattern=r"\basst_[A-Za-z0-9]{8,}\b",
        replacement="dashboard prompt id via prompt={'id': ...}",
        note="Hardcoded assistant id; swap for a dashboard prompt id after recreating the bundle.",
        target=ANY_FILE,
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
        target=ANY_FILE,
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
        target=ANY_FILE,
    ),
]
