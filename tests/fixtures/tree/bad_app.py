import asyncio
import os

from openai import AsyncOpenAI, OpenAI
from openai.helpers import AssistantEventHandler

client = OpenAI()
aclient = AsyncOpenAI()

ASSISTANT_ID = os.environ["OPENAI_ASSISTANT_ID"]
LEGACY_ID = "asst_8fVY45hU3IM6creFkVi5MBKB"


class Handler(AssistantEventHandler):
    def on_text_created(self, text):
        print(text)


def new_thread():
    return client.beta.threads.create().id


def ask(thread_id: str, question: str):
    client.beta.threads.messages.create(
        thread_id=thread_id, role="user", content=question
    )
    run = client.beta.threads.runs.create(assistant_id=ASSISTANT_ID, thread_id=thread_id)
    while run.status in ("queued", "in_progress"):
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
    steps = client.beta.threads.runs.steps.list(thread_id=thread_id, run_id=run.id)
    return steps


async def poll_all():
    runs = await aclient.beta.threads.runs.list(thread_id="t1")
    return runs


async def upload(path: str):
    await client.beta.vector_stores.files.upload(vector_store_id="vs_1", file=path)


async def stream_one():
    async with client.beta.threads.runs.stream(
        assistant_id=ASSISTANT_ID, thread_id="t2"
    ) as stream:
        async for _ in stream:
            pass
